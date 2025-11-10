"""
Celery tasks for tournaments app
"""
from django.core.cache import cache
from django.utils import timezone

from celery import shared_task

from .models import Tournament


@shared_task
def update_tournament_statuses():
    """
    Update tournament statuses based on current time
    Runs every minute via Celery Beat
    """
    now = timezone.now()

    # Update to ongoing
    updated_ongoing = Tournament.objects.filter(
        tournament_start__lte=now, tournament_end__gt=now, status="upcoming"
    ).update(status="ongoing")

    # Update to completed
    updated_completed = Tournament.objects.filter(tournament_end__lte=now, status__in=["upcoming", "ongoing"]).update(
        status="completed"
    )

    # Clear cache if any updates occurred
    if updated_ongoing > 0 or updated_completed > 0:
        cache.delete("tournaments:list:all")

    return {
        "updated_ongoing": updated_ongoing,
        "updated_completed": updated_completed,
        "timestamp": now.isoformat(),
    }
