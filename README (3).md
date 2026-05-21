# Venture Agent

A two-agent system that takes a startup description and autonomously finds real decision-makers in Qatar, enriches their contact details, and drafts a personalised outreach email — all in under two minutes.

---

## What it does

You type in what your startup does. The system does the rest.

Agent 1 searches Qatar news sources for real named executives relevant to your venture, extracts them, tries to find their LinkedIn profile and work email, then synthesises everything into a structured JSON with a market brief, ranked call targets, and a ready-to-send outreach email.

Agent 2 triggers automatically the moment Agent 1 finishes. No button press. It enriches the first target's contact details further, logs them to a CSV pipeline tracker with a follow-up date, and streams its actions back to the UI in real time.

---

## Project logic

The problem this solves: startup fellows at Utopia Studio need at least three booked discovery calls before their G0 investment review. Finding the right people in Qatar manually — scrolling LinkedIn, reading articles, copy-pasting names — was taking three to four hours per venture. The right people are constantly quoted in Qatar news sources by name and title. This system reads those sources automatically.

Why news sources instead of LinkedIn: LinkedIn blocks scraping. Tavily returns job postings from LinkedIn (URLs with /jobs/) not real profiles, and the LLM was reading job titles as person names. Qatar news sources like Zawya, Gulf Times, and The Peninsula quote real executives constantly and Tavily can scrape them freely.

Why two agents: Agent 1 is a research and synthesis agent. Agent 2 is an action agent. Keeping them separate means the handoff is explicit — Agent 1 emits a structured HANDOFF event, Agent 2 consumes it. Neither agent needs to know how the other works internally.

---

## Flow

```
User input (venture description)
        │
        ▼
Agent 1 ── generates 8 Tavily search queries targeting Qatar news sources
        │
        ▼
        ── runs queries through Tavily (basic depth, 5 results each)
        │
        ▼
        ── filters out job posting URLs (/jobs/, /company/, /school/)
        │
        ▼
        ── LLM extraction pass (Llama 3.1 8B via Groq)
           mines article text for named executives with title + company
        │
        ▼
        ── LinkedIn search per person
           Tavily searches "Name" "Company" site:linkedin.com/in
           LLM verifies company name appears in snippet before accepting URL
        │
        ▼
        ── Hunter.io email lookup per person (25 free/month)
        │
        ▼
        ── if fewer than 5 verified people found, runs fallback rounds
           at advanced depth with different query angles (up to 3 rounds)
        │
        ▼
        ── synthesis (Llama 3.3 70B via Groq)
           produces market brief + ranked call targets + outreach email
        │
        ▼
        ── sector relevance filter
           LLM validates each target's company against the venture
           drops anyone with no plausible connection
        │
        ▼
        yields RESULT (full JSON) then HANDOFF (first target + outreach)
        │
        ▼
Agent 2 ── receives HANDOFF automatically
        │
        ▼
        ── enriches contact: LinkedIn, email (Hunter.io), phone, website, twitter
           scrapes company page as fallback for phone and social links
        │
        ▼
        ── simulates email send (logs to console)
        │
        ▼
        ── logs to outreach_log.csv with follow-up date set 2 days out
        │
        ▼
        ── generates follow-up email template
        │
        ▼
        yields AGENT2_RESULT (contact card + follow-up)
```

---

## File structure

```
venture-agent/
├── agent.py           # Agent 1 — orchestrates search, extraction, enrichment, synthesis
├── outreach_agent.py  # Agent 2 — enrichment, logging, follow-up on HANDOFF
├── server.py          # Flask server — chains both agents in one streaming response
├── extract.py         # LLM extraction of named people from raw search results
├── search.py          # Tavily query runner
├── queries.py         # LLM query generation (initial + fallback rounds)
├── enrich.py          # LinkedIn lookup (Tavily + LLM) and email lookup (Hunter.io)
├── synthesize.py      # Final synthesis via Llama 3.3 70B + sector relevance filter
├── config.py          # API clients and model config
├── cli.py             # Run from terminal without the web UI
└── index.html         # Web UI
```

---

## How to run

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/venture-agent.git
cd venture-agent
```

### 2. Install dependencies

```bash
pip install flask openai tavily-python requests
```

### 3. Set up your API keys

Create a `.env` file in the root folder:

```
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
HUNTER_API_KEY=your_hunter_key
```

Get your keys here:
- Groq (free): https://console.groq.com
- Tavily (free tier available): https://tavily.com
- Hunter.io (25 free lookups/month): https://hunter.io

### 4. Run the server

```bash
python server.py
```

Open `http://localhost:5000` in your browser.

### 5. Or run from terminal

```bash
python cli.py "B2B SaaS for last-mile logistics optimisation in Qatar"
```

---

## Prompts used

### Query generation — Agent 1, Round 1
Used in `queries.py` via Llama 3.1 8B (Groq).

```
You are a research strategist. Generate 8 search queries to find market intelligence
and real named people for this venture in Qatar.

Venture: "{venture}"

Rules:
- Every query MUST include "Qatar" or "Doha"
- Queries 1-2: target zawya.com OR arabianbusiness.com — find named executives
  with title in this sector Qatar
- Queries 3-4: target gulf-times.com OR thepeninsulaqatar.com — named executives
  or companies in this sector Qatar
- Query 5: press release OR announcement — top company in this sector Qatar +
  "appoints" OR "names" OR "welcomes"
- Query 6: qatarfreezones.qa OR qatarchamber.com — member companies or named officials
- Query 7: conference OR summit Qatar 2024 2025 — speakers list for this sector
- Query 8: market overview — key companies, market size, recent deals Qatar

Do NOT use site:linkedin.com — LinkedIn blocks scrapers and returns job postings not people.

Return ONLY a JSON array of 8 strings.
```

### People extraction — Agent 1
Used in `extract.py` via Llama 3.1 8B (Groq).

```
Extract real individual people from the text below. Humans only — not companies,
brands, or places.

IMPORTANT — these sources include:
- News articles from zawya.com, gulf-times.com, arabianbusiness.com, thepeninsulaqatar.com
- LinkedIn posts (URLs containing /posts/) — these are extremely valuable: a post often
  says "Patrick Moebel, President of FedEx Express Middle East, visited QFZ today" —
  that is a confirmed real person. Mine these aggressively.
- Company press releases and event coverage — sentences like "X, Title at Company,
  said..." are confirmed people.

For each person extract:
- name: full name (First Last) — skip single names or usernames
- title: exact job title from source (null if not stated)
- company: their employer from source (null if not stated)
- url: the URL they appeared at

Rules:
- Mine news articles and LinkedIn posts aggressively for named executives
- Do NOT guess or infer missing fields
- Arabic names are valid — include them
- A sentence structure like "[Name], [Title] at [Company], said/announced/visited..."
  is a confirmed person — always include them

Return ONLY a JSON array.
```

### LinkedIn verification — Agent 1
Used in `enrich.py` via Llama 3.1 8B (Groq). Runs after Tavily returns candidate URLs.

```
Does this LinkedIn profile belong to this exact person?

Person: {name}
Company (MUST appear in snippet to be valid): {company}

URL: {url}
Snippet: {snippet}

Rules:
- Reply YES only if the snippet explicitly mentions "{company}" or a clear abbreviation
- Reply NO if the company is absent or a different company appears
- Reply NO if you are not confident

Reply with only YES or NO.
```

### Sector relevance filter — Agent 1
Used in `synthesize.py` via Llama 3.1 8B (Groq). Runs after synthesis to drop weak matches.

```
Venture: {venture}

Below are proposed discovery call targets. For each, decide if their company could
be a potential customer or partner for this venture.

Keep the target if their company:
- Moves physical goods (delivery, freight, 3PL, courier, logistics, last-mile)
- Operates in e-commerce, retail, food distribution, cold chain, warehousing
- Is a free zone operator, port authority, or transport authority in Qatar/GCC
- Is a freight forwarder, customs broker, or trade facilitation company
- Is a chamber of commerce, trade association, or industry body for logistics/trade
- Provides supply chain technology, fleet management, or route optimisation
- Is a government body overseeing trade, ports, customs, or transport in Qatar/GCC

Drop the target ONLY if their company is clearly and obviously unrelated.
When in doubt, KEEP the target.

For each target, respond with ONLY: "KEEP" or "DROP". One word per line.
```

### Final synthesis — Agent 1
Used in `synthesize.py` via Llama 3.3 70B (Groq). The main synthesis call.

System prompt:
```
You are a venture discovery agent built for Utopia Studio — a startup studio in Doha, Qatar.

Your role is to help early-stage founders prepare for their G0 (Gate Zero) investment review.
G0 requirement: the fellow must walk in with AT LEAST 3 booked discovery calls, including
at least one Qatar-based customer.

RULES:
- Use ONLY people from the VERIFIED PEOPLE list provided. Do NOT invent or hallucinate any person.
- QATAR FIRST: prioritise Qatar-based targets.
- QUALITY GATE: Only include a person if they have BOTH a real job title AND a real company name.
- Set data_confidence honestly: "high" = name + title + company + source URL all confirmed.
- The outreach message must reference the first target's actual company and role.
- pipeline_notes must be one sentence the fellow can say verbatim at the weekly call.
- Return ONLY valid JSON.

Return EXACTLY this structure:
{
  "venture": "...",
  "generated_at": "...",
  "market_brief": {
    "segments": [...],
    "pain_points": [...],
    "key_players": [...]
  },
  "call_targets": [
    {
      "name": "...", "title": "...", "company": "...", "location": "...",
      "rationale": "...", "source_url": "...",
      "data_confidence": "high/medium/low", "is_qatar_based": true/false
    }
  ],
  "outreach_message": {
    "to": "...", "subject": "...", "body": "..."
  },
  "pipeline_notes": "...",
  "gap_note": null
}
```

---

## APIs and tools called

| Tool | What it does in this system |
|---|---|
| Groq (Llama 3.1 8B) | Query generation, people extraction, LinkedIn verification, sector filter |
| Groq (Llama 3.3 70B) | Final synthesis — market brief, targets, outreach email |
| Tavily | Web search and scraping of Qatar news sources + LinkedIn profile search |
| Hunter.io | Work email lookup by name and company domain |
| Flask | Web server and streaming response handler |

---

## Known limitations

- Hunter.io free plan is 25 lookups per month. Emails will show empty after the quota runs out.
- LinkedIn URL matching fails for very common Arabic names where the company name doesn't appear in the Tavily snippet. The system returns empty rather than guess wrong.
- Apollo was tested and removed. Coverage for Qatar executives on the free plan was near zero.
- Email sending is simulated. No actual emails are sent in the current version.
