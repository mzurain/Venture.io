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


def _confidence(title: str, company: str, url: str) -> str:
    has_title   = bool(title   and title.lower().strip()   not in _NULL)
    has_company = bool(company and company.lower().strip() not in _NULL)
    has_url     = bool(url     and url.startswith("http"))
    score = sum([has_title, has_company, has_url])
    return "high" if score == 3 else "medium" if score == 2 else "low"


def _is_skip_url(url: str) -> bool:
    url_lower = url.lower()
    return any(frag in url_lower for frag in _SKIP_URL_FRAGMENTS)


def _extract_batch(blocks: list[str]) -> list:
    combined = "---\n".join(blocks)

    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""Extract real individual people from the text below. Humans only — not companies, brands, or places.

IMPORTANT — these sources include:
- News articles from zawya.com, gulf-times.com, arabianbusiness.com, qatarfreezones.qa, press releases
- LinkedIn posts (URLs containing /posts/) — these are extremely valuable: a post often says
  "Patrick Moebel, President of FedEx Express Middle East, visited QFZ today" — that is a confirmed real person. Mine these aggressively.
- Company press releases and event coverage — sentences like "X, Title at Company, said..." are confirmed people.

For each person extract:
- name: full name (First Last) — skip single names or usernames
- title: exact job title from source (null if not stated)
- company: their employer from source (null if not stated)
- url: the URL they appeared at

Rules:
- Mine news articles and LinkedIn posts aggressively for named executives — this is the primary signal
- Do NOT guess or infer missing fields
- Only include people with a clear professional context
- Include people even if only title OR company is found (not both required)
- Arabic names are valid — include them
- A sentence structure like "[Name], [Title] at [Company], said/announced/visited..." is a confirmed person — always include them

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

        if title.lower()   in _NULL: title   = ""
        if company.lower() in _NULL: company = ""

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
