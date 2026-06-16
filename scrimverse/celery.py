"""
Celery configuration for Scrimverse
"""
import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")

app = Celery("scrimverse")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    "update-tournament-statuses": {
        "task": "tournaments.tasks.tournament_tasks.update_tournament_statuses",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "cleanup-unpaid-tournaments-registrations": {
        "task": "tournaments.tasks.tournament_tasks.cleanup_unpaid_tournaments_and_registrations",
        "schedule": crontab(minute=0),  # Run every hour at minute 0
    },
    "update-platform-statistics": {
        "task": "tournaments.tasks.tournament_tasks.update_platform_statistics",
        "schedule": crontab(minute=5),  # Run every hour at minute 5
    },
    "refresh-host-dashboards": {
        "task": "tournaments.tasks.tournament_tasks.refresh_all_host_dashboards",
        "schedule": crontab(minute="*/10"),  # Run every 10 minutes
    },
    "update-leaderboard": {
        "task": "tournaments.tasks.score_tasks.update_leaderboard",
        "schedule": crontab(minute="*/30"),  # Run every 30 minutes
    },
    "send-tournament-reminders-24h": {
        "task": "tournaments.tasks.email_tasks.send_tournament_reminders_24h",
        "schedule": crontab(minute=0),  # Run every hour at minute 0
    },
    "send-tournament-reminders-1h": {
        "task": "tournaments.tasks.email_tasks.send_tournament_reminders_1h",
        "schedule": crontab(minute="*/5"),  # Run every 5 minutes
    },
    "notify-credential-release": {
        "task": "tournaments.tasks.tournament_tasks.notify_credential_release",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "notify-match-credential-release": {
        "task": "tournaments.tasks.tournament_tasks.notify_match_credential_release",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "notify-slot-list-release": {
        "task": "tournaments.tasks.tournament_tasks.notify_slot_list_release",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "notify-match-start": {
        "task": "tournaments.tasks.tournament_tasks.notify_match_start",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "check-temp-team-conversions": {
        "task": "tournaments.tasks.check_temp_team_conversions",
        "schedule": crontab(minute="*"),  # Run every minute, same as status updates
    },
    "cleanup-expired-temp-teams": {
        "task": "tournaments.tasks.cleanup_expired_temp_teams",
        "schedule": crontab(minute=30),  # Run every hour at minute 30
    },
    "send-temp-team-24h-reminders": {
        "task": "tournaments.tasks.send_temp_team_24h_reminders",
        "schedule": crontab(minute=15),  # Run every hour at minute 15
    },
}

app.conf.timezone = "Asia/Kolkata"


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
