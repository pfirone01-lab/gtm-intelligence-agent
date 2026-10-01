import os

from core.agent import create_chat_completion
from core.tools import query_supabase, send_email

SYSTEM_PROMPT = """You are a GTM pipeline analyst. You will be given raw lead data
from the most recent 7-day period and the 7 days before that. Compare the two
periods and identify 3 to 5 things that changed meaningfully: lead volume,
conversion rate by source, or average score. Do not just repeat the numbers,
say what they mean.

Format your response as one short sentence per line, with a blank line between
each point, so it reads as a readable list rather than one dense paragraph.
Do not use bullet points or numbering, just plain sentences separated by blank
lines."""


def run_pipeline_check() -> str:
    this_week_sql = """
        SELECT lead_source, COUNT(*) as total,
               AVG(CASE WHEN status = 'Closed Won' THEN 1 ELSE 0 END) as conversion_rate,
               AVG(score) as avg_score
        FROM leads
        WHERE created_at >= (SELECT MAX(created_at) FROM leads) - INTERVAL '7 days'
        GROUP BY lead_source
    """
    last_week_sql = """
        SELECT lead_source, COUNT(*) as total,
               AVG(CASE WHEN status = 'Closed Won' THEN 1 ELSE 0 END) as conversion_rate,
               AVG(score) as avg_score
        FROM leads
        WHERE created_at >= (SELECT MAX(created_at) FROM leads) - INTERVAL '14 days'
          AND created_at < (SELECT MAX(created_at) FROM leads) - INTERVAL '7 days'
        GROUP BY lead_source
    """

    this_week_data = query_supabase(this_week_sql)
    last_week_data = query_supabase(last_week_sql)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Most recent 7 days: {this_week_data}\n\nPrior 7 days: {last_week_data}"}
    ]

    response = create_chat_completion(messages=messages)
    pipeline_summary = response.choices[0].message.content

    send_email(
        subject="Daily GTM Pipeline Check",
        body=pipeline_summary,
        recipient_email=os.environ["NOTIFICATION_RECIPIENT_EMAIL"]
    )

    return pipeline_summary


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(run_pipeline_check())