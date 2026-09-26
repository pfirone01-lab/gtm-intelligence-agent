# GTM Intelligence Agent

An autonomous, code-first GTM research agent built with Python and Groq's free LLM API, featuring tool-calling, structured outputs, and scheduled automation. No no-code tools involved.

This is a flagship portfolio project demonstrating raw agent engineering: an LLM that reasons about which tools to call, executes real Python functions, and produces structured, actionable output, entirely on free-tier infrastructure.

---

## What it does

The agent runs in three modes, all sharing one core reasoning engine:

1. **On-demand company research** (`modes/research.py`, exposed via `app.py` and `index.html`) — given a company name, the agent decides which web searches to run, gathers real-time information, and returns a structured brief: summary, recent news, employee estimate, industry, suggested talking points, and a draft outreach message. Results are persisted to Supabase.

2. **Daily pipeline health monitor** (`modes/pipeline_monitor.py`) — runs on a schedule, pulls lead data from Supabase, compares the current period to the prior one, and writes a short, plain-English analysis of what changed and why it matters, not just a table of numbers.

3. **Pre-meeting briefing agent** (`modes/meeting_briefing.py`) — checks Google Calendar for upcoming meetings with external attendees and automatically researches the company or context before the meeting starts.

---

## Architecture

```
gtm_agent/
├── core/
│   ├── agent.py          # Reasoning loop, tool schema, model fallback logic
│   ├── tools.py          # Tavily search, Supabase read/write, time utility
│   └── calendar_tool.py  # Google Calendar OAuth + event fetching
├── modes/
│   ├── research.py           # Mode 1: on-demand company research
│   ├── pipeline_monitor.py   # Mode 2: daily pipeline analysis
│   └── meeting_briefing.py   # Mode 3: pre-meeting briefings
├── app.py            # Flask API exposing Mode 1 to the frontend
├── index.html         # Frontend UI for Mode 1
├── scheduler.py        # Always-on process running Modes 2 and 3 on a timer
└── requirements.txt
```

All three modes route through the same tool-calling core in `core/agent.py`: the model receives a task and a list of available tools (web search, database queries, calendar access), decides what to call, executes it, and reasons over the result before producing a final structured answer.

---

## Tech stack (100% free tier)

| Layer | Tool | Notes |
|---|---|---|
| LLM reasoning + tool calling | Groq API (`openai/gpt-oss-20b`, with `openai/gpt-oss-120b` as an automatic fallback on rate limits) | No credit card required |
| Web research | Tavily Search API | 1,000 free credits/month |
| Structured data | Supabase (PostgreSQL) | Shared with the SQL Lead Analytics Dashboard project |
| Calendar access | Google Calendar API | Free for personal use |
| Scheduling | Python `schedule` library | No external cron service needed |
| Hosting | Render Background Worker | 750 free hours/month |
| Frontend | Static HTML/CSS/JS | No framework, calls the Flask API directly |

---

## Setup

1. Clone the repo and create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

2. Create a `.env` file with:
   ```
   GROQ_API_KEY=
   TAVILY_API_KEY=
   SUPABASE_URL=
   SUPABASE_KEY=
   SUPABASE_SERVICE_KEY=
   ```

3. Set up Google Calendar OAuth credentials (`credentials.json`) via Google Cloud Console for Mode 3.

4. Run each piece independently:
   ```
   python -m modes.research        # test Mode 1 from the terminal
   python app.py                   # start the Mode 1 API + frontend
   python -m modes.pipeline_monitor
   python -m modes.meeting_briefing
   python scheduler.py             # runs Modes 2 and 3 on a schedule
   ```

---

## Known limitations

- **Model accuracy**: this project runs entirely on free, open-weight models (Groq's `gpt-oss-20b`/`120b`). Smaller models occasionally hallucinate or misstate specific facts when summarizing search results. Structured facts (dates, figures, claims) should be spot-checked before being acted on or shared externally, a known and disclosed limitation of LLM-summarized web search, not something any prompt fully eliminates.
- **Recency**: search results are time-filtered where possible, but publisher metadata isn't always reliable, so occasional stale results can surface even with recency filters applied.
- **Concurrency**: Groq's free tier applies rate limits at the account level, not per-user. The current implementation includes retry logic and a client-side cooldown to stay within these limits during solo testing and demos. A production deployment supporting many concurrent users would need request queuing, response caching for repeat lookups, and a paid inference tier.
- **Google Calendar**: currently configured for personal/testing use (OAuth "testing" mode with a manually added test user). A production version for an organization would need Google's app verification process and a domain-based (rather than single-email) filter for identifying external meeting attendees.

---

## Development note

This project was built using an AI-accelerated workflow to maximize delivery speed. While AI handled the boilerplate syntax, I acted as the System Architect, defining the data flows, establishing strict error handling for API rate limits, and designing the fallback logic for failed agent states.
