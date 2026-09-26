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

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gtm_agent.api")

app = Flask(__name__)


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
    except ResearchTemporarilyUnavailableError as unavailable_error:
        logger.warning(str(unavailable_error))
        return jsonify({
            "error": "The research agent is temporarily unavailable. Please try again in a moment."
        }), 503
    except ResearchIncompleteError as incomplete_error:
        logger.warning(str(incomplete_error))
        return jsonify({"error": "Could not find enough information to build a research brief."}), 404
    except groq.RateLimitError:
        logger.warning("Groq rate limit hit for company_name=%s", company_name)
        return jsonify({"error": "Rate limit reached. Try again in a moment."}), 429
    except postgrest.exceptions.APIError as db_error:
        logger.error("Supabase write rejected: %s", db_error)
        return jsonify({"error": "Failed to persist research brief to Supabase."}), 502
    except httpx.ConnectTimeout:
        logger.error("Supabase connection timed out after retries for company_name=%s", company_name)
        return jsonify({"error": "Could not save the research brief due to a network timeout. Please try again."}), 504

    if research_brief.get("error") == "not_found":
        return jsonify({"error": f"'{company_name}' does not appear to be a real, findable company."}), 404

    return jsonify(research_brief), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)