import json
from datetime import datetime, timezone
from config import llm, MODEL, MODEL_FAST, SYSTEM_PROMPT


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw   = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        raise


def _validate_sector_relevance(venture: str, targets: list) -> list:
    if not targets:
        return []

    target_list = "\n".join(
        f"{i}. {t.get('name')} — {t.get('title')} at {t.get('company')}"
        for i, t in enumerate(targets, 1)
    )

    try:
        response = llm.chat.completions.create(
            model=MODEL_FAST,
            messages=[{
                "role": "user",
                "content": f"""Venture: {venture}

Below are proposed discovery call targets. For each, decide if their company could be a potential customer or partner for this venture.

Keep the target if their company:
- Moves physical goods (delivery, freight, 3PL, courier, logistics, last-mile)
- Operates in e-commerce, retail, food distribution, cold chain, warehousing
- Is a free zone operator, port authority, or transport authority in Qatar/GCC
- Is a freight forwarder, customs broker, or trade facilitation company
- Is a chamber of commerce, trade association, or industry body for logistics/trade
- Operates cargo, ground handling, or aviation logistics (airports, airlines with cargo ops)
- Provides supply chain technology, fleet management, or route optimisation
- Is a government body overseeing trade, ports, customs, or transport in Qatar/GCC

Drop the target ONLY if their company is clearly and obviously unrelated with no plausible logistics angle:
- Pure residential real estate developers, pure retail banking, pure oil & gas extraction (no logistics arm), pure construction (no supply chain ops), pure software vendors that are direct competitors.
- When in doubt, KEEP the target.

Targets:
{target_list}

For each target (1, 2, 3...), respond with ONLY: "KEEP" or "DROP".
One word per line, no explanation.

Example:
KEEP
DROP
KEEP"""
            }],
            temperature=0.2,
            max_tokens=80
        )

        verdicts = response.choices[0].message.content.strip().split("\n")
        filtered = []

        for i, target in enumerate(targets):
            if i < len(verdicts):
                verdict = verdicts[i].strip().upper()
                if verdict == "KEEP":
                    filtered.append(target)

        if len(filtered) == 0 and len(targets) >= 2:
            filtered = targets[:2]

        return filtered

    except Exception:
        return targets


def synthesize(
    venture: str,
    people: list,
    all_context: list[str],
    all_raw: list,
    tried_queries: list[str]
) -> dict:
    combined = "\n\n---\n\n".join(all_context)
    if len(combined) > 6000:
        combined = combined[:6000] + "\n...[truncated for token limit]"

    if people:
        lines = "\n".join(
            f"{i}. {p['name']} | {p['title']} | {p['company']} | {p['url']} | confidence:{p['data_confidence']}"
            for i, p in enumerate(people[:15], 1)
        )
        people_section = f"VERIFIED PEOPLE — use ONLY these, exclude anyone with null title or null company:\n{lines}"
    else:
        people_section = (
            "VERIFIED PEOPLE: none found with both a confirmed job title and company name. "
            "Set call_targets to []. Write a gap_note with 3-5 specific manual steps: "
            "exact LinkedIn search strings using site:linkedin.com/in/ with relevant titles and Qatar, "
            "named company leadership pages to check, and relevant Qatar/GCC conference speaker lists "
            "— all tailored specifically to this venture."
        )

    user_message = f"""Venture: {venture}

WEB RESEARCH ({len(all_raw)} sources, {len(tried_queries)} queries):
{combined}

{people_section}

Instructions:
- call_targets from verified people only — real title + real company required
- Qatar-based targets first; set is_qatar_based correctly
- If fewer than 3 pass quality gate, set gap_note with specific manual steps for this venture
- pipeline_notes: one sentence for the Radical Asia / A-Typical Ventures weekly call
- Return valid JSON only"""

    response = llm.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        temperature=0.2,
        max_tokens=3500
    )

    result = _parse_json(response.choices[0].message.content)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    original_targets = result.get("call_targets", [])
    if original_targets:
        filtered_targets = _validate_sector_relevance(venture, original_targets)
        result["call_targets"] = filtered_targets

        if len(filtered_targets) < len(original_targets):
            dropped = len(original_targets) - len(filtered_targets)
            result["gap_note"] = (
                result.get("gap_note") or ""
            ) + (
                f" [{dropped} target(s) removed due to weak sector alignment. "
                f"Recommend manual validation of remaining {len(filtered_targets)} targets.]"
            )

    return result
