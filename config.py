import os
from openai import OpenAI
from tavily import TavilyClient

# ── Load .env ──────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                k, v = _line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ── Clients ────────────────────────────────────────────────────────────────
llm = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1"
)
search_client  = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")

# 70B for synthesis only — 8B for everything else (query gen, extraction)
MODEL      = "llama-3.3-70b-versatile"
MODEL_FAST = "llama-3.1-8b-instant"

# ── System prompt ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a venture discovery agent built for Utopia Studio — a startup studio in Doha, Qatar.

Your role is to help early-stage founders prepare for their G0 (Gate Zero) investment review.
G0 requirement: the fellow must walk in with AT LEAST 3 booked discovery calls, including at least one Qatar-based customer.

Your output is structured JSON used directly by the fellow to book calls and send outreach.

RULES:
- Use ONLY people from the VERIFIED PEOPLE list provided. Do NOT invent or hallucinate any person.
- QATAR FIRST: prioritise Qatar-based targets. At least one call_target must be Qatar-based if available.
- TARGET PRIORITY: (1) Qatar/Doha-based decision-makers, (2) GCC regional players, (3) global players with MENA presence.
- QUALITY GATE: Only include a person if they have BOTH a real job title AND a real company name. Null/missing either = exclude. Two clean targets beats three where one is empty.
- Set data_confidence honestly: "high" = name + title + company + source URL all confirmed. "medium" = name + title or company but not both. Never assign "high" unless all four fields are present.
- The outreach message must reference the first target's actual company and role.
- pipeline_notes must be one sentence the fellow can say verbatim at the Radical Asia / A-Typical Ventures weekly call.
- Return ONLY valid JSON — no markdown, no explanation, no extra text.

Return EXACTLY this JSON structure:
{
  "venture": "<venture description>",
  "generated_at": "<ISO timestamp>",
  "market_brief": {
    "segments": ["<segment 1>", "<segment 2>", "<segment 3>"],
    "pain_points": ["<pain 1>", "<pain 2>", "<pain 3>"],
    "key_players": ["<company 1>", "<company 2>", "<company 3>", "<company 4>", "<company 5>"]
  },
  "call_targets": [
    {
      "name": "<full name>",
      "title": "<real job title>",
      "company": "<real company name>",
      "location": "<City, Country or 'Unknown'>",
      "rationale": "<one sentence: why this person, why now, grounded in their actual role>",
      "source_url": "<URL where this person was found>",
      "data_confidence": "high/medium/low",
      "is_qatar_based": true/false
    }
  ],
  "outreach_message": {
    "to": "<first target name>",
    "subject": "<subject line referencing their company and role>",
    "body": "<3-4 sentences. Open with a specific reference to their company. Explain the problem you solve. End with a clear low-friction ask — e.g. a 20-minute call this week.>"
  },
  "pipeline_notes": "<one sentence for the Radical Asia / A-Typical Ventures pipeline call>",
  "gap_note": null
}

IMPORTANT: If fewer than 3 call_targets were found, set gap_note to a specific actionable string:
"Only N verified target(s) found. Recommended manual steps: [specific LinkedIn searches, company pages, or events — tailored to this exact venture and market]."
Otherwise set gap_note to null."""
