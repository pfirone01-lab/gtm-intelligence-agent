import os
import json

import groq
from groq import Groq
from dotenv import load_dotenv
from core.tools import get_current_time, tavily_search

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)

PRIMARY_MODEL = "openai/gpt-oss-20b"
FALLBACK_MODEL = "openai/gpt-oss-120b"

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current date and time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "Searches the web and returns a summary of top results for a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search phrase to look up. For recent news, include the "
                            "current year explicitly in the query text, since this biases "
                            "search ranking toward current results more reliably than the "
                            "time_range filter alone."
                        )
                    },
                    "time_range": {
                        "type": "string",
                        "enum": ["none", "day", "week", "month", "year"],
                        "description": (
                            "Restricts results to this recent time window. Use 'month' for "
                            "recent news or developments, 'year' for facts that update "
                            "periodically (like employee counts), and 'none' for stable facts "
                            "(like what a company fundamentally does)."
                        )
                    }
                },
                "required": ["query", "time_range"]
            }
        }
    }
]

available_functions = {
    "get_current_time": get_current_time,
    "tavily_search": tavily_search
}


def create_chat_completion(**request_kwargs):
    try:
        return client.chat.completions.create(model=PRIMARY_MODEL, **request_kwargs)
    except groq.RateLimitError:
        # Separate models draw from separate rate-limit buckets on Groq, so a
        # 429 on the primary model doesn't imply the fallback is also limited.
        return client.chat.completions.create(model=FALLBACK_MODEL, **request_kwargs)


def run_agent(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]

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

        second_response = create_chat_completion(messages=messages)
        return second_response.choices[0].message.content

    return reply.content


if __name__ == "__main__":
    answer = run_agent("Search the web and tell me what Anthropic does.")
    print(answer)