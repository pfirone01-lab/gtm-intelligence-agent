import os
import time
import logging

import httpx
import requests
from tavily import TavilyClient
from supabase import create_client

logger = logging.getLogger("gtm_agent.tools")

TAVILY_MAX_RETRIES = 3
TAVILY_RETRY_BACKOFF_SECONDS = 2
TAVILY_MAX_RESULTS = 3
TAVILY_SNIPPET_CHAR_LIMIT = 500
TAVILY_VALID_TIME_RANGES = {"day", "week", "month", "year"}

SUPABASE_MAX_RETRIES = 3
SUPABASE_RETRY_BACKOFF_SECONDS = 2


def get_current_time() -> str:
    from datetime import datetime
    return f"The current date and time is {datetime.now().strftime('%B %d, %Y, %I:%M:%S %p')}"

def tavily_search(query: str, time_range: str = "none") -> str:
    tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    # Groq's tool schema validation rejects an empty string against an enum,
    # so "none" is passed explicitly as a real enum value from the model
    # rather than relying on it to omit the field, which it proved unreliable
    # at doing. Filtering it out here restores "no time filter" behavior for
    # Tavily's own call.
    search_kwargs = {"query": query, "max_results": 5}
    if time_range in TAVILY_VALID_TIME_RANGES:
        search_kwargs["time_range"] = time_range

    for attempt in range(1, TAVILY_MAX_RETRIES + 1):
        try:
            search_results = tavily_client.search(**search_kwargs)
            break
        except requests.exceptions.ConnectionError as connection_error:
            logger.warning(
                "Tavily connection reset on attempt %d/%d for query='%s': %s",
                attempt, TAVILY_MAX_RETRIES, query, connection_error
            )
            if attempt == TAVILY_MAX_RETRIES:
                return f"Search temporarily unavailable for '{query}' after {TAVILY_MAX_RETRIES} attempts."
            time.sleep(TAVILY_RETRY_BACKOFF_SECONDS * attempt)

    if not search_results["results"]:
        no_results_suffix = f" within the last {time_range}." if time_range != "none" else "."
        return f"No results found for '{query}'{no_results_suffix}"

    # Publish dates are surfaced explicitly per result so the model can anchor
    # "when" something happened to real data instead of inferring or guessing
    # a date, which was previously producing fabricated timestamps.
    return "\n".join(
        f"- {result['title']} ({result.get('published_date', 'date unknown')}): "
        f"{result['content'][:TAVILY_SNIPPET_CHAR_LIMIT]}"
        for result in search_results["results"][:TAVILY_MAX_RESULTS]
    )


def save_research_brief(research_brief: dict) -> str:
    supabase_client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    for attempt in range(1, SUPABASE_MAX_RETRIES + 1):
        try:
            supabase_client.table("research_briefs").insert(research_brief).execute()
            return "Saved to Supabase."
        except httpx.ConnectTimeout as timeout_error:
            logger.warning(
                "Supabase connect timeout on attempt %d/%d: %s",
                attempt, SUPABASE_MAX_RETRIES, timeout_error
            )
            if attempt == SUPABASE_MAX_RETRIES:
                raise
            time.sleep(SUPABASE_RETRY_BACKOFF_SECONDS * attempt)


def query_supabase(sql: str) -> str:
    supabase_client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    query_result = supabase_client.rpc("execute_sql", {"query": sql}).execute()
    return str(query_result.data)