import os
import datetime
import logging

from modes.pipeline_monitor import run_pipeline_check
from modes.meeting_briefing import check_for_upcoming_meetings
from core.tools import send_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gtm_agent.scheduled_checks")

DAILY_PIPELINE_CHECK_HOUR_UTC = 7  # roughly 8am Africa/Lagos (UTC+1)
DEVELOPER_ALERT_EMAIL = os.environ.get("DEVELOPER_ALERT_EMAIL", os.environ.get("NOTIFICATION_RECIPIENT_EMAIL"))


def _alert_developer(check_name: str, error: Exception) -> None:
    # A failure inside this alert path itself must not raise, since that
    # would mask the original error with a new, unrelated one; the original
    # failure is already fully logged above regardless of whether this
    # notification succeeds.
    try:
        send_email(
            subject=f"[GTM Agent] {check_name} failed",
            body=f"{check_name} raised an exception:\n\n{error}",
            recipient_email=DEVELOPER_ALERT_EMAIL
        )
    except Exception as alert_error:
        logger.error("Failed to send developer alert email: %s", alert_error, exc_info=True)


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
            _alert_developer("Daily pipeline check", unexpected_error)

    try:
        briefings = check_for_upcoming_meetings()
        if briefings:
            logger.info("Generated %d meeting briefing(s).", len(briefings))
        else:
            logger.info("No qualifying meetings in the next hour.")
    except Exception as unexpected_error:
        logger.error("Meeting briefing check failed: %s", unexpected_error, exc_info=True)
        _alert_developer("Meeting briefing check", unexpected_error)


if __name__ == "__main__":
    main()