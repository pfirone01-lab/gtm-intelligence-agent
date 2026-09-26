import time
import logging

import schedule
from dotenv import load_dotenv

from modes.pipeline_monitor import run_pipeline_check
from modes.meeting_briefing import check_for_upcoming_meetings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gtm_agent.scheduler")


def run_daily_pipeline_check() -> None:
    try:
        pipeline_summary = run_pipeline_check()
        logger.info("Daily pipeline check completed:\n%s", pipeline_summary)
    except Exception as unexpected_error:
        # This is the one place a broad except is appropriate: an unattended
        # scheduler must never crash and stop running future jobs because one
        # scheduled run failed, so every failure mode is logged and swallowed
        # at this top level rather than allowed to kill the process.
        logger.error("Daily pipeline check failed: %s", unexpected_error, exc_info=True)


def run_meeting_briefing_check() -> None:
    try:
        briefings = check_for_upcoming_meetings()
        if briefings:
            logger.info("Generated %d meeting briefing(s).", len(briefings))
        else:
            logger.info("No qualifying meetings in the next hour.")
    except Exception as unexpected_error:
        logger.error("Meeting briefing check failed: %s", unexpected_error, exc_info=True)


schedule.every().day.at("08:00").do(run_daily_pipeline_check)
schedule.every(20).minutes.do(run_meeting_briefing_check)

if __name__ == "__main__":
    logger.info("Scheduler started. Pipeline check daily at 08:00, meeting check every 20 minutes.")
    while True:
        schedule.run_pending()
        time.sleep(30)