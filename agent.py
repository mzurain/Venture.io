import json
from queries    import generate_initial_queries, generate_fallback_queries
from search     import run_query_batch
from extract    import extract_people, merge_people
from enrich     import enrich_people
from synthesize import synthesize

_TARGET_FLOOR = 5
_MAX_ROUNDS   = 3


def run_agent_streaming(venture_description: str):
    yield f"LOG:→ venture: {venture_description}"
    yield "LOG:  generating search queries..."

    all_context    = []
    all_raw        = []
    tried_queries  = []
    people         = []
    all_people     = []

    try:
        queries = generate_initial_queries(venture_description)
    except Exception as e:
        yield f"ERROR:Failed to generate queries: {str(e)}"
        return

    yield f"LOG:  running {len(queries)} Tavily searches (round 1)..."
    context, raw = run_query_batch(queries, depth="basic")
    people       = extract_people(raw)
    all_people.extend(people)

    all_context.append(context)
    all_raw.extend(raw)
    tried_queries.extend(queries)
    yield f"LOG:  round 1 — {len(people)} verified people from {len(raw)} sources"

    if people:
        yield f"LOG:  enriching {len(people)} people (LinkedIn + Hunter email)..."
        try:
            people     = enrich_people(people)
            all_people = enrich_people(all_people)
            enriched   = sum(1 for p in people if p.get("email"))
            yield f"LOG:  enrichment done — {enriched}/{len(people)} emails found"
        except Exception as e:
            yield f"LOG:  ⚠ enrichment failed: {str(e)}"

    round_num = 1
    while len(people) < _TARGET_FLOOR and round_num <= _MAX_ROUNDS:
        round_num += 1
        yield f"LOG:  ⚠ only {len(people)} verified — fallback round {round_num} (advanced depth)..."

        try:
            queries = generate_fallback_queries(venture_description, len(people), tried_queries)
        except Exception as e:
            yield f"LOG:  ⚠ fallback query generation failed: {str(e)}"
            break

        context, raw   = run_query_batch(queries, depth="advanced")
        new_people     = extract_people(raw)

        if new_people:
            try:
                new_people = enrich_people(new_people)
            except Exception:
                pass

        people         = merge_people(people, new_people)
        all_people     = merge_people(all_people, new_people)

        all_context.append(context)
        all_raw.extend(raw)
        tried_queries.extend(queries)
        yield f"LOG:  round {round_num} — {len(people)} verified people across {len(all_raw)} sources"

    if len(people) == 0:
        yield "LOG:  ⚠ no verified people found — gap_note will guide manual steps"
    elif len(people) < _TARGET_FLOOR:
        yield f"LOG:  ⚠ {len(people)} verified people — proceeding, gap_note will be set"
    else:
        yield f"LOG:  ✓ {len(people)} verified people — synthesizing..."

    yield "LOG:  building market brief, targets, and outreach..."

    try:
        result = synthesize(venture_description, people, all_context, all_raw, tried_queries)
    except Exception as e:
        yield f"ERROR:Synthesis failed: {str(e)}"
        return

    targets     = result.get("call_targets", [])
    qatar_count = sum(1 for t in targets if t.get("is_qatar_based"))

    if len(targets) < _TARGET_FLOOR and not result.get("gap_note"):
        result["gap_note"] = (
            f"Only {len(targets)} verified target(s) found across "
            f"{len(tried_queries)} searches and {len(all_raw)} sources. "
            "Recommended manual steps: search zawya.com and arabianbusiness.com for "
            "decision-makers with titles relevant to this sector in Qatar/GCC; check "
            "'Leadership' pages of key players in the market brief; look for speakers "
            "at recent GCC industry conferences."
        )

    result["extraction_metadata"] = {
        "people_found":     len(people),
        "all_people_count": len(all_people),
        "queries_run":      len(tried_queries),
        "sources_scraped":  len(all_raw),
        "search_rounds":    round_num,
        "data_quality": (
            "good"     if len(targets) >= 5 else
            "adequate" if len(targets) >= 3 else
            "limited"
        )
    }

    result["all_people"] = all_people

    yield f"LOG:✓ done — {len(targets)} targets ({qatar_count} Qatar-based)"
    if result.get("gap_note"):
        yield "LOG:  ⚠ gap_note set — see output for manual steps"

    yield f"RESULT:{json.dumps(result)}"

    first_target = targets[0] if targets else None
    outreach     = result.get("outreach_message", {})

    if first_target and outreach.get("body"):
        handoff_payload = {
            "target": {
                "name":       first_target.get("name", ""),
                "title":      first_target.get("title", ""),
                "company":    first_target.get("company", ""),
                "location":   first_target.get("location", ""),
                "source_url": first_target.get("source_url", ""),
                "email":      first_target.get("email", ""),
            },
            "outreach": {
                "subject": outreach.get("subject", ""),
                "body":    outreach.get("body", ""),
            },
            "all_targets": targets,
        }
        yield f"HANDOFF:{json.dumps(handoff_payload)}"
    else:
        yield "LOG:  ⚠ no valid target for Agent 2 handoff — skipping"
