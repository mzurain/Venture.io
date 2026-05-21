import json
import sys
from agent import run_agent_streaming


def run_agent(venture_description: str) -> dict | None:
    print(f"\n→ Running discovery agent for: {venture_description}\n")
    result = None
    for event in run_agent_streaming(venture_description):
        if event.startswith("LOG:"):
            print(" ", event[4:])
        elif event.startswith("RESULT:"):
            result = json.loads(event[7:])
        elif event.startswith("ERROR:"):
            print(f"✗ ERROR: {event[6:]}")
    return result


def print_output(result: dict):
    if not result:
        print("\n✗ Agent failed to produce output")
        return

    sep = "=" * 70
    print(f"\n{sep}\nDISCOVERY AGENT OUTPUT\n{sep}")
    print(f"\nVenture:   {result.get('venture')}")
    print(f"Generated: {result.get('generated_at')}")

    meta = result.get("extraction_metadata", {})
    print(
        f"People found: {meta.get('people_found', 0)} | "
        f"Queries run: {meta.get('queries_run', 0)} | "
        f"Sources: {meta.get('sources_scraped', 0)} | "
        f"Quality: {meta.get('data_quality', 'unknown')}"
    )

    brief = result.get("market_brief", {})
    print("\n── MARKET BRIEF " + "─" * 54)
    print("\nSegments:");    [print(f"  • {s}") for s in brief.get("segments", [])]
    print("\nPain Points:"); [print(f"  • {p}") for p in brief.get("pain_points", [])]
    print("\nKey Players:"); [print(f"  • {k}") for k in brief.get("key_players", [])]

    print("\n── CALL TARGETS " + "─" * 54)
    targets = result.get("call_targets", [])
    if targets:
        print(f"\nFound {len(targets)} targets:\n")
        for i, t in enumerate(targets, 1):
            flag = " 🇶🇦" if t.get("is_qatar_based") else ""
            print(f"  {i}. {t.get('name')}{flag} — {t.get('title')}, {t.get('company')}")
            print(f"     Location:   {t.get('location', 'Unknown')}")
            print(f"     Rationale:  {t.get('rationale')}")
            print(f"     Confidence: {t.get('data_confidence', 'unknown')}")
            print(f"     Source:     {t.get('source_url', 'N/A')}\n")
    else:
        print("\n  No verified targets found.")

    gap = result.get("gap_note")
    if gap:
        print("\n── ⚠ GAP NOTE " + "─" * 56)
        print(f"\n  {gap}\n")

    outreach = result.get("outreach_message", {})
    if outreach.get("to"):
        print("\n── OUTREACH EMAIL (Target #1) " + "─" * 40)
        print(f"\n  To:      {outreach.get('to')}")
        print(f"  Subject: {outreach.get('subject')}")
        print(f"\n  {outreach.get('body')}")

    pipeline = result.get("pipeline_notes", "")
    if pipeline:
        print("\n── PIPELINE CALL NOTE " + "─" * 48)
        print(f"\n  → {pipeline}")

    print(f"\n{sep}\nRAW JSON\n{sep}")
    print(json.dumps(result, indent=2))


def save_output(result: dict, venture: str):
    if not result:
        return
    filename = venture.lower().replace(" ", "_")[:40].strip("_") + "_output.json"
    with open(filename, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✓ Saved to {filename}")


if __name__ == "__main__":
    venture = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    if not venture:
        print("\n" + "=" * 70)
        print("DISCOVERY AGENT")
        print("=" * 70 + "\n")
        venture = input("Enter your venture description: ").strip()
    if not venture:
        print("No venture provided.")
        sys.exit(1)

    result = run_agent(venture)
    if result:
        print_output(result)
        save_output(result, venture)
