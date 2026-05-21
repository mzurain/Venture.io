import json
from config import llm, MODEL_FAST

_NULL = {"null", "none", "title not found", "company not found", "unknown", "n/a", ""}
_BATCH_SIZE = 10

_SKIP_URL_FRAGMENTS = (
    "linkedin.com/jobs/",
    "linkedin.com/company/",
    "linkedin.com/school/",
    "/jobs/",
    "/job-detail/",
    "/careers/",
    "/vacancies/",
)

# Titles that are almost always journalists or article authors, not executives
_JOURNALIST_TITLE_SIGNALS = (
    "reporter",
    "correspondent",
    "editor",
    "journalist",
    "staff writer",
    "contributor",
    "author",
    "columnist",
)


def _confidence(title: str, company: str, url: str) -> str:
    has_title   = bool(title   and title.lower().strip()   not in _NULL)
    has_company = bool(company and company.lower().strip() not in _NULL)
    has_url     = bool(url     and url.startswith("http"))
    score = sum([has_title, has_company, has_url])
    return "high" if score == 3 else "medium" if score == 2 else "low"


def _is_skip_url(url: str) -> bool:
    url_lower = url.lower()
    return any(frag in url_lower for frag in _SKIP_URL_FRAGMENTS)


def _is_journalist(title: str, company: str) -> bool:
    title_lower = title.lower()
    return any(signal in title_lower for signal in _JOURNALIST_TITLE_SIGNALS)


def _extract_batch(blocks: list[str]) -> list:
    combined = "---\n".join(blocks)

    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""Extract real individual people from the text below. Humans only — not companies, brands, or places.

These sources are news articles and press releases. They contain two types of people:
1. EXECUTIVES — the people we want. Named in the article body as decision-makers, quoted with their title and company.
2. JOURNALISTS — the people we do NOT want. The author or reporter who wrote the article. These appear in bylines, "Written by", "By [Name]", author boxes, or at the very top/bottom of the article with no company mentioned.

For each person extract:
- name: full name (First Last) — skip single names or usernames
- title: exact job title from source (null if not stated)
- company: their employer from source (null if not stated)
- url: the URL they appeared at

Rules:
- INCLUDE people quoted or mentioned in the article body with a clear business title and company — "Francisco De Sousa, Managing Director of talabat, said..." is a confirmed executive
- EXCLUDE anyone who appears to be the article's author or journalist — "By [Name]", "Written by [Name]", "[Name] is a reporter at Gulf Times" — skip these entirely
- EXCLUDE people with titles like reporter, correspondent, editor, journalist, staff writer, contributor, columnist
- EXCLUDE heads of state, royalty, or political figures (presidents, prime ministers, ministers, sheikhs in political roles) unless they are directly relevant as a business decision-maker
- Do NOT guess or infer missing fields
- Arabic names are valid — include them
- Only include people with a clear professional business context

Return ONLY a JSON array, no markdown, no explanation:
[{{"name": "...", "title": "...", "company": "...", "url": "..."}}]

If none found, return: []

TEXT:
{combined}"""
        }],
        temperature=0,
        max_tokens=2000
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        parts = raw.split("```")
        raw   = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        raise


def extract_people(raw_results: list) -> list:
    if not raw_results:
        return []

    blocks    = []
    seen_urls = set()

    for r in raw_results:
        url = r.get("url", "")

        if _is_skip_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        text = (r.get("raw_content") or r.get("content") or "")[:600]
        if text.strip():
            blocks.append(f"URL: {url}\n{text}")

    if not blocks:
        return []

    all_raw_people = []
    for i in range(0, len(blocks), _BATCH_SIZE):
        batch = blocks[i : i + _BATCH_SIZE]
        try:
            people = _extract_batch(batch)
            if isinstance(people, list):
                all_raw_people.extend(people)
        except Exception as e:
            print(f"  [extract] batch {i//_BATCH_SIZE + 1} failed: {e}")
            continue

    cleaned, seen = [], set()

    for p in all_raw_people:
        if not isinstance(p, dict):
            continue

        name    = (p.get("name")    or "").strip()
        title   = (p.get("title")   or "").strip()
        company = (p.get("company") or "").strip()
        url     = (p.get("url")     or "").strip()

        if not name or len(name.split()) < 2:
            continue
        if "linkedin.com/company/" in url or "linkedin.com/school/" in url:
            continue
        if name.lower() in seen:
            continue

        if title.lower() in _NULL: title   = ""
        if company.lower() in _NULL: company = ""

        # Post-extraction journalist filter as a safety net
        if _is_journalist(title, company):
            continue

        conf = _confidence(title, company, url)
        if conf == "low":
            continue

        seen.add(name.lower())
        cleaned.append({
            "name":            name,
            "title":           title   or "Title not found",
            "company":         company or "Company not found",
            "url":             url,
            "data_confidence": conf,
            "is_qatar_based":  any(
                term in (title + " " + company + " " + url).lower()
                for term in ["qatar", "doha", "doḥa"]
            )
        })

    return cleaned


def merge_people(existing: list, new_batch: list) -> list:
    seen = {p["name"].lower() for p in existing}
    for p in new_batch:
        if p["name"].lower() not in seen:
            existing.append(p)
            seen.add(p["name"].lower())
    return existing
