import os
import json

from core.agent import create_chat_completion, tools_schema, available_functions
from core.calendar_tool import get_upcoming_events
from core.tools import send_email

SYSTEM_PROMPT = """You are a GTM meeting-prep assistant. You will be given context
about an upcoming meeting, either a company name, a person's email domain, or a
meeting title. Use the tavily_search tool to find whatever you can about who or
what this meeting involves: company info, recent news, or context about the topic.

If you genuinely cannot find anything useful, it's fine to say so briefly rather
than inventing details.

Then respond with ONLY a JSON object, no other text, in exactly this shape:
{
  "who": "...",
  "company_summary": "...",
  "recent_news": "...",
  "talking_point": "...",
  "suggested_question": "..."
}
"""

MY_EMAIL = "philemonfirone0@gmail.com"

GENERIC_EMAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"
}


def get_external_attendee(event: dict) -> tuple[str | None, str | None]:
    attendees = event.get("attendees", [])
    for attendee in attendees:
        email = attendee.get("email", "")
        if email and email.lower() != MY_EMAIL.lower():
            domain = email.split("@")[-1].lower()
            return domain, email
    return None, None


def build_research_context(event: dict, domain: str | None, email: str) -> str:
    """
    Decides what to actually hand the model to research. Prefers a real
    company domain. Falls back to the meeting title if the domain is just
    a generic personal email provider with no company signal.
    """
    title = event.get("summary", "Untitled meeting")

    if domain and domain not in GENERIC_EMAIL_PROVIDERS:
        return f"Company domain: {domain}, attendee email: {email}, meeting title: {title}"

    return f"No company domain available (attendee uses a personal email: {email}). Meeting title: {title}"


def generate_briefing(research_context: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Prepare a briefing for this meeting: {research_context}"}
    ]

    raw_response_text = None
    for _ in range(8):
        response = create_chat_completion(messages=messages, tools=tools_schema)
        reply = response.choices[0].message

        if reply.tool_calls:
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
            continue

        raw_response_text = reply.content
        break

    if raw_response_text is None:
        return {"error": "Agent ran out of tool-call rounds without a final answer"}

    try:
        return json.loads(raw_response_text)
    except json.JSONDecodeError:
        return {"error": "Could not parse briefing", "raw": raw_response_text}


def _format_briefing_as_email_body(briefing: dict) -> str:
    # A plain, readable layout is used here rather than raw JSON, since this
    # text is the actual message a person reads in their inbox, not a
    # machine-to-machine payload.
    if briefing.get("error"):
        return f"Could not generate a full briefing.\n\nDetails: {briefing['error']}\n{briefing.get('raw', '')}"

    return (
        f"Meeting: {briefing.get('meeting_title', 'Untitled meeting')}\n"
        f"Who: {briefing.get('who', 'Unknown')}\n\n"
        f"Company summary:\n{briefing.get('company_summary', 'N/A')}\n\n"
        f"Recent news:\n{briefing.get('recent_news', 'N/A')}\n\n"
        f"Talking point:\n{briefing.get('talking_point', 'N/A')}\n\n"
        f"Suggested question:\n{briefing.get('suggested_question', 'N/A')}"
    )


def check_for_upcoming_meetings() -> list[dict]:
    events = get_upcoming_events(hours_ahead=1)
    briefings = []

    for event in events:
        domain, email = get_external_attendee(event)
        if not email:
            continue

        research_context = build_research_context(event, domain, email)
        briefing = generate_briefing(research_context)
        briefing["meeting_title"] = event.get("summary", "Untitled meeting")
        briefing["start_time"] = event.get("start")
        briefings.append(briefing)

        send_email(
            subject=f"Meeting Briefing: {briefing['meeting_title']}",
            body=_format_briefing_as_email_body(briefing),
            recipient_email=os.environ["NOTIFICATION_RECIPIENT_EMAIL"]
        )

    return briefings


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results = check_for_upcoming_meetings()
    if not results:
        print("No qualifying meetings with external attendees in the next hour.")
    else:
        for briefing in results:
            print(json.dumps(briefing, indent=2))