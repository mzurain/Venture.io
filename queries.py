import json
from config import llm, MODEL_FAST


def _parse_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw   = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def generate_initial_queries(venture: str) -> list[str]:
    """
    8 targeted Tavily queries: market intel + people signals.
    Targets news/press sources (zawya, gulf-times, arabianbusiness, qatarfreezones.qa,
    Hamad Port, QTerminals, GWC press pages) which name real executives freely.
    site:linkedin.com avoided — LinkedIn blocks Tavily scraping.
    Uses MODEL_FAST.
    """
    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""You are a research strategist. Generate 8 search queries to find market intelligence and real named people for this venture in Qatar.

Venture: "{venture}"

Rules:
- Every query MUST include "Qatar" or "Doha" (not just GCC)
- Queries 1-2: target zawya.com OR arabianbusiness.com — find named executives with title in this sector Qatar
  Example format: site:zawya.com "logistics" Qatar CEO OR director 2024
- Queries 3-4: target gulf-times.com OR thepeninsulaqatar.com — named executives or companies in this sector Qatar
- Query 5: press release OR announcement — top company in this sector Qatar + "appoints" OR "names" OR "welcomes" — these always name executives
- Query 6: qatarfreezones.qa OR qatarchamber.com — member companies or named officials in this sector
- Query 7: conference OR summit Qatar 2024 2025 — speakers list for this sector (names real executives)
- Query 8: market overview — key companies, market size, recent deals Qatar — zawya OR arabianbusiness

Be highly specific to the venture description. No generic queries.
Do NOT use site:linkedin.com — LinkedIn blocks scrapers and returns job postings not people.

Return ONLY a JSON array of 8 strings, no preamble, no markdown:
["query 1", "query 2", ..., "query 8"]"""
        }],
        temperature=0.4,
        max_tokens=600
    )
    return _parse_list(response.choices[0].message.content)


def generate_fallback_queries(venture: str, found_count: int, tried: list[str]) -> list[str]:
    """
    8 fresh queries when fewer than 3 verified people found.
    Completely different angles. Targets news/press/government sources.
    Uses MODEL_FAST.
    """
    tried_str = "\n".join(f"- {q}" for q in tried)

    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""Previous searches found only {found_count} verified people. We need more.

Venture: "{venture}"

Already tried — do NOT repeat or paraphrase:
{tried_str}

Generate 8 NEW queries with completely different angles targeting sources that NAME real executives:
1. site:al-sharq.com OR site:peninsula.qa — named executive in this sector Qatar (Arabic news source)
2. "management team" OR "our leadership" — specific company in this sector Qatar (company about-us pages name executives)
3. Crunchbase OR wamda.com — GCC founders or CEOs in this sector
4. Qatar government body OR regulator overseeing this sector + "director general" OR "CEO" OR "chairman"
5. Press release: specific Qatar company in this sector + "CEO" OR "managing director" announces 2024 OR 2025
6. Industry report Qatar — zawya OR oxford economics — will cite named experts
7. Trade show OR exhibition Qatar 2024 2025 keynote speaker — names real executives
8. "Hamad Port" OR "QTerminals" OR "GWC" OR "Milaha" OR relevant Qatar operator + "head of" OR "director"

Every query MUST include "Qatar" or "Doha".
Do NOT use site:linkedin.com.

Return ONLY a JSON array of 8 strings, no preamble, no markdown:
["query 1", "query 2", ..., "query 8"]"""
        }],
        temperature=0.6,
        max_tokens=600
    )
    return _parse_list(response.choices[0].message.content)


def extract_titles_for_apollo(venture: str) -> list[str]:
    """
    Kept for backwards compatibility — now used only as title hints for
    Hunter.io enrichment and synthesis, not for Apollo (which is removed).
    Returns 6 relevant job titles for this venture.
    Uses MODEL_FAST.
    """
    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""For this venture: "{venture}"

List 6 job titles that would belong to the ideal B2B discovery call target — decision-makers who would buy or champion this product.
Be specific to the industry. Use common LinkedIn title formats.

Return ONLY a JSON array of 6 strings:
["title 1", "title 2", ..., "title 6"]"""
        }],
        temperature=0.3,
        max_tokens=200
    )
    try:
        return _parse_list(response.choices[0].message.content)
    except Exception:
        return ["director", "head of operations", "supply chain manager", "VP logistics", "founder", "CEO"]


def generate_apollo_keywords(venture: str) -> str:
    """
    Kept for backwards compatibility — generates industry keyword string.
    Now used as context for synthesis rather than Apollo queries.
    Uses MODEL_FAST.
    """
    response = llm.chat.completions.create(
        model=MODEL_FAST,
        messages=[{
            "role": "user",
            "content": f"""Venture: "{venture}"

List 5 short industry keywords that describe the sector of businesses that would BUY or USE this venture's product.

Rules:
- Single words or short 2-word phrases only
- Cover the core sector AND adjacent sectors
- No generic words like "technology", "solutions", "services"

Return ONLY a JSON array of 5 strings:
["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]"""
        }],
        temperature=0.3,
        max_tokens=100
    )
    try:
        terms = _parse_list(response.choices[0].message.content)
        return " OR ".join(f'"{t}"' if " " in t else t for t in terms[:5])
    except Exception:
        return "logistics OR warehouse OR operations OR supply chain OR distribution"
