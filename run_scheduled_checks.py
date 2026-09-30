import datetime
import logging

from modes.pipeline_monitor import run_pipeline_check
from modes.meeting_briefing import check_for_upcoming_meetings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gtm_agent.scheduled_checks")

DAILY_PIPELINE_CHECK_HOUR_UTC = 7  # roughly 8am Africa/Lagos (UTC+1)


def main() -> None:
    current_hour_utc = datetime.datetime.utcnow().hour

    if current_hour_utc == DAILY_PIPELINE_CHECK_HOUR_UTC:
        try:
            pipeline_summary = run_pipeline_check()
            logger.info("Daily pipeline check completed:\n%s", pipeline_summary)
        except Exception as unexpected_error:
            # GitHub Actions runs this script once per invocation and exits;
            # a broad except here ensures a single failed check doesn't fail
            # the whole workflow run and skip the meeting check below.
            logger.error("Daily pipeline check failed: %s", unexpected_error, exc_info=True)

    try:
        briefings = check_for_upcoming_meetings()
        if briefings:
            logger.info("Generated %d meeting briefing(s).", len(briefings))
        else:
            logger.info("No qualifying meetings in the next hour.")
    except Exception as unexpected_error:
        logger.error("Meeting briefing check failed: %s", unexpected_error, exc_info=True)


if __name__ == "__main__":
    main()