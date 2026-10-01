# GTM Intelligence Agent

An autonomous, code-first GTM research agent built with Python and Groq's free LLM API, featuring tool-calling, structured outputs, and scheduled automation. No no-code tools involved.

This is a flagship portfolio project demonstrating raw agent engineering: an LLM that reasons about which tools to call, executes real Python functions, and produces structured, actionable output, entirely on free-tier infrastructure.

**Live demo:** https://gtm-agent-api-uc35.onrender.com

---

## What it does

The agent runs in three modes, all sharing one core reasoning engine:

1. **On-demand company research** (`modes/research.py`, exposed via `app.py` and `index.html`) — given a company name, the agent decides which web searches to run, gathers real-time information, and returns a structured brief: summary, recent news, employee estimate, industry, suggested talking points, and a draft outreach message. Results are persisted to Supabase. Publicly accessible and mobile-responsive.

2. **Daily pipeline health monitor** (`modes/pipeline_monitor.py`) — runs on a schedule, pulls lead data from Supabase, compares the current period to the prior one, and emails a short, plain-English analysis of what changed and why it matters, not just a table of numbers.

3. **Pre-meeting briefing agent** (`modes/meeting_briefing.py`) — checks Google Calendar for upcoming meetings with external attendees and automatically researches and emails a briefing before the meeting starts.

---

## Architecture

```
gtm_agent/
├── core/
│   ├── agent.py          # Reasoning loop, tool schema, model fallback logic
│   ├── tools.py          # Tavily search, Supabase read/write, email, time utility
│   └── calendar_tool.py  # Google Calendar OAuth + event fetching
├── modes/
│   ├── research.py           # Mode 1: on-demand company research
│   ├── pipeline_monitor.py   # Mode 2: daily pipeline analysis
│   └── meeting_briefing.py   # Mode 3: pre-meeting briefings
├── .github/workflows/
│   └── scheduled-checks.yml  # Runs Modes 2 and 3 on a schedule
├── app.py               # Flask API + serves the frontend, deployed on Render
├── index.html            # Frontend UI for Mode 1 (mobile-responsive)
├── run_scheduled_checks.py  # Entry point invoked by the GitHub Actions workflow
├── Procfile              # Render start command
└── requirements.txt
```

All three modes route through the same tool-calling core in `core/agent.py`: the model receives a task and a list of available tools (web search, database queries, calendar access), decides what to call, executes it, and reasons over the result before producing a final structured answer. `create_chat_completion()` wraps every call with automatic fallback to a secondary model (`openai/gpt-oss-120b`) if the primary model's rate limit is hit.

---

## Tech stack (100% free tier)

| Layer | Tool | Notes |
|---|---|---|
| LLM reasoning + tool calling | Groq API (`openai/gpt-oss-20b`, with `openai/gpt-oss-120b` as automatic fallback) | No credit card required |
| Web research | Tavily Search API | 1,000 free credits/month |
| Structured data | Supabase (PostgreSQL) | Shared with the SQL Lead Analytics Dashboard project |
| Calendar access | Google Calendar API | Free for personal use |
| Email notifications | Gmail SMTP (App Password) | Free, used for both result delivery and developer error alerts |
| API + frontend hosting | Render (free Web Service) | Serves `app.py`, including `index.html` at `/` |
| Scheduled automation | GitHub Actions (`workflow_dispatch`) triggered externally by cron-job.org | See note below |
| Frontend | Static HTML/CSS/JS, mobile-responsive | No framework, served directly by Flask |

### A note on scheduling

GitHub Actions' built-in `schedule:` (cron) trigger is documented by GitHub as "best-effort" and was found to be unreliable in practice during this build, scheduled runs were delayed by hours or dropped entirely, a known, widely-reported platform issue as of late 2026. The workaround: the workflow still defines a `schedule:` trigger, but is additionally triggered externally and reliably via `workflow_dispatch`, called on a timer by **cron-job.org** (a free external cron service) hitting GitHub's REST API. This sidesteps GitHub's internal scheduler queue entirely.

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
   GMAIL_SENDER_ADDRESS=
   GMAIL_APP_PASSWORD=
   NOTIFICATION_RECIPIENT_EMAIL=
   DEVELOPER_ALERT_EMAIL=
   ```

3. Set up Google Calendar OAuth credentials (`credentials.json`, then `token.json` via first run) through Google Cloud Console for Mode 3.

4. Run each piece independently:
   ```
   python -m modes.research        # test Mode 1 from the terminal
   python app.py                   # start the Mode 1 API + frontend locally
   python -m modes.pipeline_monitor
   python -m modes.meeting_briefing
   python run_scheduled_checks.py  # simulate what the GitHub Actions workflow runs
   ```

5. For deployment: push to GitHub, connect the repo to a Render Web Service (Build: `pip install -r requirements.txt`, Start: `gunicorn app:app --timeout 120`), add all environment variables there, plus `GOOGLE_CREDENTIALS_JSON` and `GOOGLE_TOKEN_JSON` as GitHub Actions secrets (full contents of the respective local files) for the scheduled workflow.

---

## Known limitations

- **Model accuracy**: this project runs entirely on free, open-weight models (Groq's `gpt-oss-20b`/`120b`). Smaller models occasionally hallucinate or misstate specific facts when summarizing search results. Structured facts (dates, figures, claims) should be spot-checked before being acted on or shared externally, a known and disclosed limitation of LLM-summarized web search, not something any prompt fully eliminates.
- **Recency**: search results are time-filtered where possible and the model is instructed to anchor dates to each result's actual published date, but publisher metadata isn't always reliable, so occasional stale results can surface even with recency filters applied.
- **Concurrency**: Groq's free tier applies rate limits at the account level, not per-user. The implementation includes automatic model fallback, retry logic, and a client-side search cooldown to stay within these limits during demos. A production deployment supporting many concurrent users would need request queuing, response caching for repeat lookups, and a paid inference tier.
- **Scheduling reliability**: see the scheduling note above. GitHub Actions' native cron trigger is not currently dependable on its own; this is mitigated with an external trigger, not eliminated as a platform-level constraint.
- **Render free tier cold starts**: the live demo spins down after 15 minutes of inactivity and takes up to a minute to wake on the next request. Acceptable for a demo/portfolio link, not suitable as-is for production traffic expecting instant response.
- **Google Calendar**: currently configured for personal/testing use (OAuth "testing" mode with a manually added test user). A production version for an organization would need Google's app verification process and a domain-based (rather than single-email) filter for identifying external meeting attendees.

---

## Development note

This project was built using an AI-accelerated workflow to maximize delivery speed. While AI handled the boilerplate syntax, I acted as the System Architect, defining the data flows, establishing strict error handling for API rate limits, and designing the fallback logic for failed agent states.