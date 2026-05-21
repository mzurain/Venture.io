"""
outreach_agent.py
-----------------
Agent 2: autonomous outreach agent triggered by a HANDOFF event from Agent 1.

NOT called by a human button press — triggered automatically by agent.py
after synthesis completes. server.py chains both agents in one stream.

Actions taken autonomously on HANDOFF:
  1. Receive first call target + outreach message from Agent 1
  2. Enrich contact: verify/find email via Hunter.io (if not already enriched)
  3. Scrape company page for phone + website + Twitter as fallback
  4. Format outreach message
  5. Simulate send (log to console — no SMTP)
  6. Log to CSV pipeline tracker with follow-up date
  7. Generate follow-up reminder template
  8. Yield AGENT2: prefixed log lines back to server.py

Can also be called directly from CLI:
    python outreach_agent.py discovery_output.json
"""

import csv
import json
import os
import re
import sys
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

from enrich import find_linkedin, hunter_find_email

# ── Load .env ──────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                k, v = _line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

OUTREACH_LOG   = os.path.join(os.path.dirname(__file__), "outreach_log.csv")
LOG_FIELDS     = ["timestamp", "name", "company", "email", "subject",
                  "status", "follow_up_date", "reply_received", "call_booked"]
FOLLOW_UP_DAYS = 2

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _fetch_page(url: str, timeout: int = 10) -> str:
    try:
        r = requests.get(url, headers=_SCRAPE_HEADERS, timeout=timeout,
                         allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def _extract_phones(text: str) -> list[str]:
    pattern = re.compile(
        r'(\+?\d{1,3}[\s\-.]?\(?\d{1,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4})'
    )
    phones, seen = [], set()
    for p in pattern.findall(text):
        cleaned = re.sub(r'[\s\-.]', '', p)
        if 7 <= len(cleaned) <= 16 and cleaned not in seen:
            seen.add(cleaned)
            phones.append(p.strip())
    return phones


def _extract_twitter(text: str) -> str:
    m = re.search(
        r'(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,50})(?:["\'/?\s]|$)',
        text
    )
    return f"https://twitter.com/{m.group(1)}" if m else ""


def _guess_domain(company: str) -> str:
    slug = company.lower()
    for noise in ["llc", "ltd", "inc", "co.", "corp", "group", "holding",
                  "holdings", "international", "solutions", " - ", "  "]:
        slug = slug.replace(noise, " ")
    slug = slug.strip()
    first_word = _normalise(slug.split()[0]) if slug else _normalise(company)
    return f"https://www.{first_word}.com" if first_word else ""


def _guess_email_pattern(name: str, company: str) -> tuple[str, str]:
    parts = name.strip().split()
    if len(parts) < 2:
        return "", "no_email"
    first = _normalise(parts[0])
    last  = _normalise(parts[-1])
    slug  = company.lower()
    for noise in ["llc", "ltd", "inc", "co.", "corp", "group", "holding",
                  "holdings", "international", "solutions", " - ", "  "]:
        slug = slug.replace(noise, " ")
    domain = (_normalise(slug.split()[0]) if slug.strip() else _normalise(company))
    if not first or not last or not domain:
        return "", "no_email"
    return f"{first}.{last}@{domain}.com", "guess"


# ══════════════════════════════════════════════════════════════════════════════
# Contact enrichment
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_company_contacts(company: str, known_website: str = "") -> dict:
    result  = {"phone": "", "twitter": "", "website": ""}
    website = known_website or _guess_domain(company)
    if not website:
        return result
    result["website"] = website

    for url in [urljoin(website, "/contact"), urljoin(website, "/contact-us"), website]:
        html = _fetch_page(url)
        if not html:
            continue
        if not result["phone"]:
            phones = _extract_phones(html)
            if phones:
                result["phone"] = phones[0]
        if not result["twitter"]:
            tw = _extract_twitter(html)
            if tw and "twitter.com/intent" not in tw:
                result["twitter"] = tw
        if result["phone"] and result["twitter"]:
            break

    return result


def enrich_contact(target: dict) -> dict:
    """
    Full contact enrichment for a single target dict.
    Priority: Hunter.io verified email > pattern guess > not_found
    Supplements with company page scrape for phone/twitter/website.
    """
    name     = target.get("name", "")
    company  = target.get("company", "")
    linkedin = target.get("source_url") or target.get("url", "")

    contact = {
        "linkedin":     linkedin if "linkedin.com/in/" in linkedin else "",
        "email":        target.get("email", ""),    # may already be set by Hunter in agent.py
        "email_source": target.get("email_source", ""),
        "email_note":   target.get("email_note", ""),
        "phone":        "",
        "phone_source": "",
        "website":      "",
        "twitter":      "",
    }

    # ── LinkedIn: Tavily + LLM search if not already set ──────────────────
    if not contact["linkedin"]:
        title = target.get("title", "")
        found = find_linkedin(name, title, company)
        if found:
            contact["linkedin"] = found

    # ── Email: Hunter.io if not already enriched ───────────────────────────
    if not contact["email"]:
        hunter_result           = hunter_find_email(name, company)
        contact["email"]        = hunter_result["email"]
        contact["email_source"] = hunter_result["source"]
        contact["email_note"]   = hunter_result["note"]

    # ── Fallback: pattern guess if Hunter found nothing ───────────────────
    if not contact["email"]:
        guessed, source         = _guess_email_pattern(name, company)
        contact["email"]        = guessed
        contact["email_source"] = source
        contact["email_note"]   = (
            f"Could not find a verified email for {name}. "
            f"Pattern-guessed: {guessed} — verify before sending."
            if guessed else
            f"No email found for {name} at {company}. Look up manually on LinkedIn or the company website."
        )

    # ── Scrape company page for phone / twitter / website ─────────────────
    scraped = _scrape_company_contacts(company, contact.get("website", ""))
    if not contact["website"] and scraped["website"]:
        contact["website"] = scraped["website"]
    if scraped["phone"]:
        contact["phone"]        = scraped["phone"]
        contact["phone_source"] = "scrape"
    if scraped["twitter"]:
        contact["twitter"] = scraped["twitter"]

    if not contact["phone"]:
        contact["phone_source"] = "not_found"

    return contact


# ══════════════════════════════════════════════════════════════════════════════
# Send + Log
# ══════════════════════════════════════════════════════════════════════════════

def _send_simulated(to_name: str, to_email: str, subject: str, body: str) -> dict:
    if not to_name:
        return {"success": False, "message": "Target name missing — cannot send."}
    sep = "─" * 60
    print(f"\n[AGENT 2 — SIMULATED EMAIL SEND]")
    print(sep)
    print(f"To:      {to_name} <{to_email}>")
    print(f"Subject: {subject}")
    print(sep)
    print(body)
    print(sep + "\n")
    return {"success": True, "message": f"Simulated send to {to_name} <{to_email}> — logged."}


def _log_csv(name, company, email, subject, status, follow_up_date):
    file_exists = os.path.isfile(OUTREACH_LOG)
    with open(OUTREACH_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "name":           name,
            "company":        company,
            "email":          email,
            "subject":        subject,
            "status":         status,
            "follow_up_date": follow_up_date,
            "reply_received": "no",
            "call_booked":    "no",
        })


def _followup_template(name: str, subject: str) -> str:
    first = name.split()[0] if name else "there"
    return (
        f"Hi {first},\n\n"
        f"Just checking if you had a chance to see my previous email about \"{subject}\".\n\n"
        "Would you have 15 minutes sometime next week for a quick call?\n\n"
        "Happy to work around your schedule.\n\n"
        "Best,"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main: autonomous handoff handler (generator — yields AGENT2: lines)
# ══════════════════════════════════════════════════════════════════════════════

def run_outreach_agent_streaming(handoff_payload: dict):
    """
    Generator yielding AGENT2: prefixed lines.
    Called by server.py immediately after HANDOFF: is received from Agent 1.
    No human interaction required.
    """
    target   = handoff_payload.get("target", {})
    outreach = handoff_payload.get("outreach", {})

    name    = target.get("name", "")
    company = target.get("company", "")
    subject = outreach.get("subject", f"Quick question about {company}")
    body    = outreach.get("body", "")

    if not name:
        yield "AGENT2:⚠ no target name in handoff — outreach agent stopping"
        return

    yield f"AGENT2:→ Agent 2 triggered for {name} at {company}"
    yield "AGENT2:  enriching contact details..."

    contact = enrich_contact(target)

    email         = contact["email"]
    email_source  = contact["email_source"]
    email_display = email if email else "— email not found —"

    yield f"AGENT2:  email: {email_display} (source: {email_source})"
    if contact["phone"]:
        yield f"AGENT2:  phone: {contact['phone']} (source: {contact['phone_source']})"
    if contact["website"]:
        yield f"AGENT2:  website: {contact['website']}"
    if contact["twitter"]:
        yield f"AGENT2:  twitter: {contact['twitter']}"

    yield "AGENT2:  sending outreach (simulated)..."
    send_result = _send_simulated(name, email_display, subject, body)
    status      = "sent" if send_result["success"] else "failed"

    follow_up_dt   = datetime.now(timezone.utc) + timedelta(days=FOLLOW_UP_DAYS)
    follow_up_date = follow_up_dt.strftime("%Y-%m-%d")

    try:
        _log_csv(name, company, email_display, subject, status, follow_up_date)
        yield f"AGENT2:  logged to {OUTREACH_LOG}"
    except Exception as e:
        yield f"AGENT2:  ⚠ CSV log failed: {e}"

    followup = _followup_template(name, subject)

    # Yield final structured result for UI
    result = {
        "success":           send_result["success"],
        "message":           f"Outreach sent to {name}. {contact['email_note']}",
        "linkedin":          contact["linkedin"],
        "email":             email_display,
        "email_source":      email_source,
        "email_note":        contact["email_note"],
        "phone":             contact["phone"],
        "phone_source":      contact["phone_source"],
        "website":           contact["website"],
        "twitter":           contact["twitter"],
        "follow_up_date":    follow_up_date,
        "followup_template": followup,
        "all_targets": [
            f"{t.get('name')} — {t.get('title', '')} at {t.get('company', '')}"
            for t in handoff_payload.get("all_targets", [])
        ],
    }

    yield f"AGENT2:✓ done — outreach logged, follow-up set for {follow_up_date}"
    yield f"AGENT2_RESULT:{json.dumps(result)}"


# ══════════════════════════════════════════════════════════════════════════════
# Legacy entry point: called from server.py /send_outreach (button) or CLI
# ══════════════════════════════════════════════════════════════════════════════

def send_outreach_from_discovery(discovery_data: dict) -> dict:
    """
    Legacy function — still works for the /send_outreach endpoint if needed.
    Prefer the streaming handoff (run_outreach_agent_streaming) for new flows.
    """
    targets  = discovery_data.get("call_targets", [])
    outreach = discovery_data.get("outreach_message", {})

    if not targets:
        return {"success": False, "message": "No call targets in discovery result."}

    target  = targets[0]
    name    = target.get("name", "")
    company = target.get("company", "")
    subject = outreach.get("subject", f"Quick question about {company}")
    body    = outreach.get("body", "")

    if not name:
        return {"success": False, "message": "Target #1 has no name — cannot send outreach."}

    contact = enrich_contact(target)

    email        = contact["email"]
    email_source = contact["email_source"]
    email_note   = contact["email_note"]
    email_display = email if email else "— could not determine email —"

    send_result = _send_simulated(name, email_display, subject, body)
    status      = "sent" if send_result["success"] else "failed"

    follow_up_dt   = datetime.now(timezone.utc) + timedelta(days=FOLLOW_UP_DAYS)
    follow_up_date = follow_up_dt.strftime("%Y-%m-%d")
    _log_csv(name, company, email_display, subject, status, follow_up_date)
    followup = _followup_template(name, subject)

    return {
        "success":           send_result["success"],
        "message":           f"Outreach sent to {name}. {email_note}",
        "linkedin":          contact["linkedin"],
        "email":             email_display,
        "email_source":      email_source,
        "email_note":        email_note,
        "phone":             contact["phone"],
        "phone_source":      contact["phone_source"],
        "website":           contact["website"],
        "twitter":           contact["twitter"],
        "follow_up_date":    follow_up_date,
        "followup_template": followup,
        "all_targets": [
            f"{t.get('name')} — {t.get('title', '')} at {t.get('company', '')}"
            for t in targets
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python outreach_agent.py <discovery_output.json>")
        sys.exit(1)
    json_path = sys.argv[1]
    if not os.path.isfile(json_path):
        print(f"✗ File not found: {json_path}")
        sys.exit(1)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = send_outreach_from_discovery(data)
    print("\n── API Response ──────────────────────────────────────────────")
    print(json.dumps(result, indent=2))
    if result.get("followup_template"):
        print("\n── Follow-up Template ─────────────────────────────────────────")
        print(result["followup_template"])
