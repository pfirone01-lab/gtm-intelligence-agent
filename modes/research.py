import json
import time
import logging

import groq

from core.agent import create_chat_completion, tools_schema, available_functions
from core.tools import save_research_brief

logger = logging.getLogger("gtm_agent.research")

MAX_TOOL_CALL_ROUNDS = 8
RESEARCH_MAX_ATTEMPTS = 3
RESEARCH_RETRY_BACKOFF_SECONDS = 3

ICP_CONTEXT = """You work for a company selling AI-powered workflow automation
tools (n8n-based, with SQL and LLM integrations) to small and mid-sized teams
in real estate, education, and sales operations. Tailor talking points and
outreach drafts toward how automation could reduce manual work for this
specific company, when relevant to their industry."""

SYSTEM_PROMPT = f"""You are a GTM research assistant. {ICP_CONTEXT}

When given a company name, use the tavily_search tool to find: what the
company does, recent news, employee count estimate, and industry.

Call get_current_time first to establish today's actual date. When searching
for recent news, include the current year explicitly in your search query
text (e.g. "Acme Corp news 2026"), since this biases search ranking toward
current results more reliably than the time_range filter alone. Use
time_range="month" for recent news, time_range="year" for employee count, and
time_range="none" for what the company fundamentally does.

If a time-filtered search returns no results, retry that same query once with
time_range="none" rather than trying different phrasings, then move on to the
next fact regardless of outcome. A smaller or less web-visible company may
genuinely have no news from the past month, in that case say so plainly in
recent_news rather than leaving it blank or inventing something.

Never guess or complete a partial name, date, or fact from a truncated
snippet. If a detail isn't clearly stated in the search results, omit it
rather than inferring it. Use the published date shown next to each result as
the actual date of that information, do not estimate or assume a different
date, and treat any result dated more than 12 months before today's actual
date as background context, not "recent" news.

Try at most 4 distinct search queries total across all facts combined. If none
of them turn up genuine evidence this company exists, stop searching
immediately and respond with:
{{"error": "not_found"}}

Otherwise respond with exactly these keys, using an empty string for any field
you genuinely could not find real information for:
{{
  "summary": "...",
  "recent_news": "...",
  "employee_estimate": "...",
  "industry": "...",
  "suggested_talking_points": "...",
  "draft_outreach_message": "..."
}}
"""


class ResearchIncompleteError(Exception):
    """Raised when a single attempt can't produce valid JSON, even from partial research."""


class ResearchTemporarilyUnavailableError(Exception):
    """Raised only after repeated provider-level errors exhaust every retry attempt."""


def _request_structured_brief(messages: list, allow_tools: bool = True) -> dict:
    request_kwargs = {"messages": messages, "response_format": {"type": "json_object"}}
    if allow_tools:
        request_kwargs["tools"] = tools_schema
        request_kwargs["tool_choice"] = "none"

    try:
        structured_response = create_chat_completion(**request_kwargs)
    except groq.APIStatusError as status_error:
        # openai/gpt-oss-120b (the fallback model) has been observed inventing
        # a nonexistent "json"/"JSON" tool call to wrap its output even when
        # tool_choice="none" is set, a quirk the primary model doesn't share.
        # Dropping tools entirely on retry sidesteps it, since the output
        # schema is already fully specified in the system prompt.
        if allow_tools and status_error.status_code == 400:
            return _request_structured_brief(messages, allow_tools=False)
        raise

    return json.loads(structured_response.choices[0].message.content)


def _run_single_research_attempt(company_name: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Research this company: {company_name}"}
    ]

    for _ in range(MAX_TOOL_CALL_ROUNDS):
        response = create_chat_completion(messages=messages, tools=tools_schema)
        reply = response.choices[0].message

        if not reply.tool_calls:
            break

        messages.append(reply)
        for call in reply.tool_calls:
            tool_function = available_functions[call.function.name]
            tool_arguments = json.loads(call.function.arguments)
            tool_result = tool_function(**tool_arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_result
            })

    messages.append({
        "role": "user",
        "content": (
            "Now output only the JSON object described in your instructions, using "
            "whatever information you have gathered so far, even if incomplete."
        )
    })

    try:
        return _request_structured_brief(messages)
    except json.JSONDecodeError as decode_error:
        raise ResearchIncompleteError(
            f"Model could not produce valid JSON for '{company_name}' even from partial research."
        ) from decode_error


def research_company(company_name: str) -> dict:
    last_transient_error: Exception | None = None

    for attempt in range(1, RESEARCH_MAX_ATTEMPTS + 1):
        try:
            research_brief = _run_single_research_attempt(company_name)
            break
        except (groq.APIStatusError, groq.APIConnectionError) as transient_error:
            # Provider-level hiccups (rate-limit fallout, transient 400s from
            # the fallback model, connection drops) are retried silently at
            # this level, since a single flaky call shouldn't ever surface as
            # a confusing technical error to the person using the frontend.
            logger.warning(
                "Transient provider error on attempt %d/%d researching '%s': %s",
                attempt, RESEARCH_MAX_ATTEMPTS, company_name, transient_error
            )
            last_transient_error = transient_error
            if attempt < RESEARCH_MAX_ATTEMPTS:
                time.sleep(RESEARCH_RETRY_BACKOFF_SECONDS * attempt)
    else:
        raise ResearchTemporarilyUnavailableError(
            f"Repeated provider errors researching '{company_name}' after {RESEARCH_MAX_ATTEMPTS} attempts."
        ) from last_transient_error

    if research_brief.get("error") == "not_found":
        return research_brief

    research_brief["company_name"] = company_name
    save_research_brief(research_brief)
    return research_brief


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    result = research_company("Anthropic")
    print(json.dumps(result, indent=2))