import os
import re
import json
import requests
from config import search_client, llm, MODEL_FAST

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
HUNTER_BASE    = "https://api.hunter.io/v2"


def _normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _guess_domain(company: str) -> str:
    slug = company.lower()
    for noise in ["llc", "ltd", "inc", "co.", "corp", "group", "holding",
                  "holdings", "international", "solutions", " - ", "  "]:
        slug = slug.replace(noise, " ")
    slug = slug.strip()
    first_word = _normalise(slug.split()[0]) if slug else _normalise(company)
    return f"{first_word}.com" if first_word else ""


def find_linkedin(name: str, title: str, company: str) -> str:
    query = f'"{name}" "{company}" site:linkedin.com/in'

    try:
        result = search_client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=False,
            include_raw_content=False,
        )
        results = result.get("results", [])
    except Exception:
        return ""

    if not results:
        return ""

    candidates = [r for r in results if "linkedin.com/in/" in r.get("url", "")]

    if not candidates:
        return ""

    if len(candidates) == 1:
        url     = candidates[0].get("url", "")
        snippet = candidates[0].get("content", "")
        if _llm_verify_single(name, title, company, url, snippet):
            return url
        return ""

    return _llm_pick_linkedin(name, title, company, candidates)


def _llm_verify_single(name: str, title: str, company: str, url: str, snippet: str) -> bool:
    if company and company.lower() not in snippet.lower():
        return False

    try:
        resp = llm.chat.completions.create(
            model=MODEL_FAST,
            messages=[{
                "role": "user",
                "content": f"""Does this LinkedIn profile belong to this exact person?

Person: {name}
Company (MUST appear in snippet to be valid): {company}

URL: {url}
Snippet: {snippet[:400]}

Rules:
- Reply YES only if the snippet explicitly mentions "{company}" or a clear abbreviation of it
- Reply NO if the company is absent or a different company appears
- Reply NO if you are not confident

Reply with only YES or NO."""
            }],
            temperature=0,
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception:
        return False


def _llm_pick_linkedin(name: str, title: str, company: str, candidates: list) -> str:
    numbered = ""
    for i, c in enumerate(candidates, 1):
        numbered += f"\n{i}. URL: {c.get('url','')}\n   Snippet: {c.get('content','')[:250]}\n"

    candidates = [
        c for c in candidates
        if company and company.lower() in c.get("content", "").lower()
    ]
    if not candidates:
        return ""
    if len(candidates) == 1:
        url     = candidates[0].get("url", "")
        snippet = candidates[0].get("content", "")
        if _llm_verify_single(name, title, company, url, snippet):
            return url
        return ""

    try:
        resp = llm.chat.completions.create(
            model=MODEL_FAST,
            messages=[{
                "role": "user",
                "content": f"""Which LinkedIn profile URL below belongs to this exact person?

Person: {name}
Company (must be explicitly mentioned in the snippet): {company}

Candidates:
{numbered}

Rules:
- Reply with ONLY the number (1, 2, or 3) of the correct match
- If none match confidently, reply with: NONE
- Do not explain"""
            }],
            temperature=0,
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip().upper()

        if answer == "NONE":
            return ""

        try:
            idx = int(answer) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx].get("url", "")
        except ValueError:
            pass

        return ""

    except Exception:
        return ""


def hunter_find_email(name: str, company: str, domain: str = "") -> dict:
    if not HUNTER_API_KEY:
        return _no_email(name, company, "Hunter API key not configured")

    parts = name.strip().split(None, 1)
    if len(parts) < 2:
        return _no_email(name, company, "Need first + last name")

    first_name    = parts[0]
    last_name     = parts[1]
    target_domain = domain or _guess_domain(company)

    if not target_domain:
        return _no_email(name, company, "Could not determine company domain")

    try:
        resp = requests.get(
            f"{HUNTER_BASE}/email-finder",
            params={
                "domain":     target_domain,
                "first_name": first_name,
                "last_name":  last_name,
                "api_key":    HUNTER_API_KEY,
            },
            timeout=10
        )

        if resp.status_code == 401:
            return _no_email(name, company, "Hunter API key invalid")
        if resp.status_code == 429:
            return _no_email(name, company, "Hunter monthly limit reached (25/month free)")
        if resp.status_code != 200:
            return _no_email(name, company, f"Hunter HTTP {resp.status_code}")

        data  = resp.json().get("data", {})
        email = (data.get("email") or "").strip()

        if not email:
            return _no_email(name, company, "No email match found")

        score      = data.get("score", 0)
        is_webmail = data.get("webmail", False)
        sources    = data.get("sources", [])

        if is_webmail:
            return {"email": email, "source": "hunter_webmail", "confidence": "low",
                    "note": f"Hunter found webmail {email} — may be personal."}
        elif score >= 70:
            return {"email": email, "source": "hunter_verified", "confidence": "high",
                    "note": f"Hunter verified: {email} (score {score}/100, {len(sources)} source(s))"}
        elif score >= 40:
            return {"email": email, "source": "hunter_verified", "confidence": "medium",
                    "note": f"Hunter found {email} medium confidence (score {score}/100) — verify before sending."}
        else:
            return {"email": email, "source": "hunter_guess", "confidence": "low",
                    "note": f"Hunter low-confidence guess: {email} (score {score}/100) — verify manually."}

    except requests.exceptions.Timeout:
        return _no_email(name, company, "Hunter timed out")
    except Exception as e:
        return _no_email(name, company, f"Hunter error: {e}")


def _no_email(name: str, company: str, reason: str = "") -> dict:
    return {
        "email":      "",
        "source":     "not_found",
        "confidence": "",
        "note": (
            f"No verified email for {name} at {company}"
            + (f" — {reason}." if reason else ".")
            + " Check LinkedIn or company website manually."
        ),
    }


def enrich_people(people: list) -> list:
    HUNTER_FREE_LIMIT = 25
    hunter_used = 0

    for person in people:
        name    = person.get("name", "")
        company = person.get("company", "")
        title   = person.get("title", "")

        existing_url = person.get("url", "")
        if "linkedin.com/in/" in existing_url:
            person["linkedin_url"] = existing_url
        else:
            person["linkedin_url"] = find_linkedin(name, title, company)

        if hunter_used < HUNTER_FREE_LIMIT:
            hunter = hunter_find_email(name, company)
            hunter_used += 1
        else:
            hunter = _no_email(name, company, "Hunter free limit reached (25/month)")

        person["email"]        = hunter["email"]
        person["email_source"] = hunter["source"]
        person["email_note"]   = hunter["note"]

    return people
