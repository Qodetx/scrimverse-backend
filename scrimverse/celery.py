"""
Celery configuration for Scrimverse
"""
import os

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
        "task": "tournaments.tasks.update_tournament_statuses",
        "schedule": crontab(minute="*"),  # Run every minute
    },
    "cleanup-unpaid-tournaments-registrations": {
        "task": "tournaments.tasks.cleanup_unpaid_tournaments_and_registrations",
        "schedule": crontab(minute=0),  # Run every hour at minute 0
    },
    "update-platform-statistics": {
        "task": "tournaments.tasks.update_platform_statistics",
        "schedule": crontab(minute=5),  # Run every hour at minute 5
    },
    "refresh-host-dashboards": {
        "task": "tournaments.tasks.refresh_all_host_dashboards",
        "schedule": crontab(minute="*/10"),  # Run every 10 minutes
    },
    "update-leaderboard": {
        "task": "tournaments.tasks.update_leaderboard",
        "schedule": crontab(minute="*/30"),  # Run every 30 minutes
    },
}

app.conf.timezone = "Asia/Kolkata"


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
