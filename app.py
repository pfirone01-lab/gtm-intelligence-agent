from __future__ import annotations

import logging

from flask import Flask, jsonify, request, Response
from dotenv import load_dotenv
import groq
import httpx
import postgrest.exceptions

from modes.research import (
    research_company,
    ResearchIncompleteError,
    ResearchTemporarilyUnavailableError,
)
from core.tools import send_email
import os

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gtm_agent.api")

app = Flask(__name__)

DEVELOPER_ALERT_EMAIL = os.environ.get("DEVELOPER_ALERT_EMAIL", os.environ.get("NOTIFICATION_RECIPIENT_EMAIL"))


def _notify_developer(error_context: str, error: Exception) -> None:
    # A failure here must never raise back up into the request handler, since
    # that would replace a clean error response with an unrelated crash; the
    # original error is already fully logged by the caller regardless of
    # whether this notification itself succeeds.
    try:
        send_email(
            subject=f"[GTM Agent API] {error_context}",
            body=f"{error_context}\n\n{type(error).__name__}: {error}",
            recipient_email=DEVELOPER_ALERT_EMAIL
        )
    except Exception as alert_error:
        logger.error("Failed to send developer alert email: %s", alert_error, exc_info=True)


@app.after_request
def allow_frontend_origin(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/research", methods=["POST", "OPTIONS"])
def research() -> tuple[Response, int]:
    if request.method == "OPTIONS":
        return jsonify({}), 200

    request_payload = request.get_json(silent=True)
    if not request_payload:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    company_name = request_payload.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "company_name is required."}), 400

    try:
        research_brief = research_company(company_name)
    except ResearchIncompleteError as incomplete_error:
        # Not treated as a backend failure: this means the agent genuinely
        # couldn't assemble enough information, functionally the same
        # "nothing found" outcome as an explicit not_found result, so no
        # developer alert is warranted here.
        logger.warning(str(incomplete_error))
        return jsonify({"error": "not_found", "message": f"Could not find enough information on '{company_name}'."}), 404
    except ResearchTemporarilyUnavailableError as unavailable_error:
        logger.warning(str(unavailable_error))
        _notify_developer(f"Repeated provider errors for company_name={company_name}", unavailable_error)
        return jsonify({"error": "service_down", "message": "The research agent is temporarily unavailable."}), 503
    except groq.RateLimitError as rate_limit_error:
        logger.warning("Groq rate limit hit for company_name=%s", company_name)
        _notify_developer(f"Groq rate limit exhausted for company_name={company_name}", rate_limit_error)
        return jsonify({"error": "service_down", "message": "Rate limit reached."}), 429
    except groq.APIStatusError as status_error:
        logger.error("Groq API error for company_name=%s: %s", company_name, status_error)
        _notify_developer(f"Groq API status error for company_name={company_name}", status_error)
        return jsonify({"error": "service_down", "message": "The LLM provider returned an unexpected error."}), 502
    except postgrest.exceptions.APIError as db_error:
        logger.error("Supabase write rejected: %s", db_error)
        _notify_developer(f"Supabase write rejected for company_name={company_name}", db_error)
        return jsonify({"error": "service_down", "message": "Failed to persist the research brief."}), 502
    except httpx.ConnectTimeout as timeout_error:
        logger.error("Supabase connection timed out for company_name=%s", company_name)
        _notify_developer(f"Supabase connect timeout for company_name={company_name}", timeout_error)
        return jsonify({"error": "service_down", "message": "A network timeout occurred while saving results."}), 504
    except Exception as unexpected_error:
        # A live API handling real user traffic must never return a bare
        # stack trace; any exception type not explicitly anticipated above
        # is still caught here, logged in full, and alerted on, rather than
        # surfacing Flask's default unhandled-exception page to the person
        # using the frontend.
        logger.error("Unhandled exception for company_name=%s: %s", company_name, unexpected_error, exc_info=True)
        _notify_developer(f"Unhandled exception for company_name={company_name}", unexpected_error)
        return jsonify({"error": "service_down", "message": "An unexpected error occurred."}), 500

    if research_brief.get("error") == "not_found":
        return jsonify({"error": "not_found", "message": f"'{company_name}' does not appear to be a real, findable company."}), 404

    return jsonify(research_brief), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)