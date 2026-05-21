import json
import sys
from agent import run_agent_streaming


def run_agent(venture_description: str) -> dict | None:
    print(f"\nRunning discovery agent for: {venture_description}\n")
    result = None
    for event in run_agent_streaming(venture_description):
        if event.startswith("LOG:"):
            print(" ", event[4:])
        elif event.startswith("RESULT:"):
            result = json.loads(event[7:])
        elif event.startswith("ERROR:"):
            print(f"ERROR: {event[6:]}")
    return result


def print_output(result: dict):
    if not result:
        print("\nAgent failed to produce output")
        return

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
    print("\nMarket Brief")
    print("Segments:");    [print(f"  • {s}") for s in brief.get("segments", [])]
    print("Pain Points:"); [print(f"  • {p}") for p in brief.get("pain_points", [])]
    print("Key Players:"); [print(f"  • {k}") for k in brief.get("key_players", [])]

    print("\nCall Targets")
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
        print(f"\nGap note: {gap}\n")

    outreach = result.get("outreach_message", {})
    if outreach.get("to"):
        print("\nOutreach Email")
        print(f"  To:      {outreach.get('to')}")
        print(f"  Subject: {outreach.get('subject')}")
        print(f"\n  {outreach.get('body')}")

    pipeline = result.get("pipeline_notes", "")
    if pipeline:
        print(f"\nPipeline note: {pipeline}")

    print("\nRaw JSON:")
    print(json.dumps(result, indent=2))


def save_output(result: dict, venture: str):
    if not result:
        return
    filename = venture.lower().replace(" ", "_")[:40].strip("_") + "_output.json"
    with open(filename, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {filename}")


if __name__ == "__main__":
    venture = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    if not venture:
        venture = input("Enter your venture description: ").strip()
    if not venture:
        print("No venture provided.")
        sys.exit(1)

    result = run_agent(venture)
    if result:
        print_output(result)
        save_output(result, venture)
