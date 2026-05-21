# Venture.io

A two-agent system that takes a startup description and finds real decision-makers in Qatar, enriches their contact details, and drafts a personalised outreach email — all in under two minutes.

---

## What it does

You type in what your startup does. The system does the rest.

**Agent 1** searches Qatar news sources for real named executives relevant to your venture, extracts them, finds their LinkedIn profile and work email, then produces a structured JSON with a market brief, ranked call targets, and a ready-to-send outreach email.

**Agent 2** triggers automatically the moment Agent 1 finishes. It enriches the first target's contact details further, logs them to a CSV pipeline tracker with a follow-up date, and streams its actions back to the UI in real time.

---

## Why this exists

Startup fellows at Utopia Studio need at least three booked discovery calls before their G0 investment review. Finding the right people in Qatar manually — scrolling LinkedIn, reading articles, copy-pasting names — was taking three to four hours per venture.

The right people are constantly quoted in Qatar news sources by name and title. This system reads those sources automatically.

**Why news sources instead of LinkedIn:** LinkedIn blocks scraping. Tavily returns job postings from LinkedIn URLs (`/jobs/`) not real profiles, and the model was reading job titles as person names. Qatar news sources like Zawya, Gulf Times, and The Peninsula quote real executives constantly and Tavily can scrape them freely.

**Why two agents:** Agent 1 is a research and synthesis agent. Agent 2 is an action agent. Keeping them separate means the handoff is explicit — Agent 1 emits a structured `HANDOFF` event, Agent 2 consumes it. Neither agent needs to know how the other works internally.

---

## How it works

```
User input (venture description)
        │
        ▼
Agent 1 — generates 8 Tavily search queries targeting Qatar news sources
        │
        ▼
        — runs queries through Tavily (basic depth, 5 results each)
        │
        ▼
        — filters out job posting URLs (/jobs/, /company/, /school/)
        │
        ▼
        — LLM extraction pass (Llama 3.1 8B via Groq)
          mines article text for named executives with title + company
        │
        ▼
        — LinkedIn search per person
          Tavily searches "Name" "Company" site:linkedin.com/in
          LLM verifies company name appears in snippet before accepting URL
        │
        ▼
        — Hunter.io email lookup per person (25 free/month)
        │
        ▼
        — if fewer than 5 verified people found, runs fallback rounds
          at advanced depth with different query angles (up to 3 rounds)
        │
        ▼
        — synthesis (Llama 3.3 70B via Groq)
          produces market brief + ranked call targets + outreach email
        │
        ▼
        — sector relevance filter
          LLM validates each target's company against the venture
          drops anyone with no plausible connection
        │
        ▼
        yields RESULT (full JSON) then HANDOFF (first target + outreach)
        │
        ▼
Agent 2 — receives HANDOFF automatically
        │
        ▼
        — enriches contact: LinkedIn, email (Hunter.io), phone, website, twitter
          scrapes company page as fallback for phone and social links
        │
        ▼
        — simulates email send (logs to console)
        │
        ▼
        — logs to outreach_log.csv with follow-up date set 2 days out
        │
        ▼
        — generates follow-up email template
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

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/mzurain/Venture.io.git
cd Venture.io
```

### 2. Install dependencies

```bash
pip install flask openai tavily-python requests
```

### 3. Add your API keys

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

## APIs used

| Tool | Purpose |
|---|---|
| Groq (Llama 3.1 8B) | Query generation, people extraction, LinkedIn verification, sector filter |
| Groq (Llama 3.3 70B) | Final synthesis — market brief, targets, outreach email |
| Tavily | Web search and scraping of Qatar news sources + LinkedIn profile search |
| Hunter.io | Work email lookup by name and company domain |
| Flask | Web server and streaming response handler |

---

## Known limitations

- Hunter.io free plan is 25 lookups per month. Emails will show empty after the quota runs out.
- LinkedIn URL matching can fail for very common Arabic names where the company name doesn't appear in the Tavily snippet. The system returns empty rather than guess wrong.
- Apollo was tested and removed — coverage for Qatar executives on the free plan was near zero.
- Email sending is simulated. No actual emails are sent in the current version.
