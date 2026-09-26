from core.agent import client, tools_schema, available_functions
from core.calendar_tool import get_upcoming_events
import json

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

MY_EMAIL = "philemonfirone0@gmail.com"  # your own calendar account's email

# Personal email providers aren't companies, so a domain match here means
# we have no real company signal from the email alone.
GENERIC_EMAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"
}


def get_external_attendee(event):
    attendees = event.get("attendees", [])
    for attendee in attendees:
        email = attendee.get("email", "")
        if email and email.lower() != MY_EMAIL.lower():
            domain = email.split("@")[-1].lower()
            return domain, email
    return None, None


def build_research_context(event, domain, email):
    """
    Decides what to actually hand the model to research. Prefers a real
    company domain. Falls back to the meeting title if the domain is just
    a generic personal email provider with no company signal.
    """
    title = event.get("summary", "Untitled meeting")

    if domain and domain not in GENERIC_EMAIL_PROVIDERS:
        return f"Company domain: {domain}, attendee email: {email}, meeting title: {title}"

    return f"No company domain available (attendee uses a personal email: {email}). Meeting title: {title}"


def generate_briefing(research_context):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Prepare a briefing for this meeting: {research_context}"}
    ]

    raw_text = None
    for _ in range(8):
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            tools=tools_schema
        )
        reply = response.choices[0].message

        if reply.tool_calls:
            messages.append(reply)
            for call in reply.tool_calls:
                func = available_functions[call.function.name]
                args = json.loads(call.function.arguments)
                result = func(**args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result
                })
            continue

        raw_text = reply.content
        break

    if raw_text is None:
        return {"error": "Agent ran out of tool-call rounds without a final answer"}

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Could not parse briefing", "raw": raw_text}


def check_for_upcoming_meetings():
    events = get_upcoming_events(hours_ahead=1)
    briefings = []

    for event in events:
        domain, email = get_external_attendee(event)
        if email:
            context = build_research_context(event, domain, email)
            briefing = generate_briefing(context)
            briefing["meeting_title"] = event.get("summary", "Untitled meeting")
            briefing["start_time"] = event.get("start")
            briefings.append(briefing)

    return briefings


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results = check_for_upcoming_meetings()
    if not results:
        print("No qualifying meetings with external attendees in the next hour.")
    else:
        for b in results:
            print(json.dumps(b, indent=2))