"""
Test cases for Celery tasks in tournaments app
"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

import pytest

from tests.factories import TournamentFactory
from tournaments.tasks import update_tournament_statuses


@pytest.mark.django_db
def test_update_upcoming_to_ongoing(host_user):
    now = timezone.now()
    tournament = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=1),
        tournament_end=now + timedelta(hours=5),
    )
    result = update_tournament_statuses()
    tournament.refresh_from_db()
    assert tournament.status == "ongoing"
    assert result["updated_ongoing"] == 1
    assert result["updated_completed"] == 0
    assert "timestamp" in result


@pytest.mark.django_db
def test_update_upcoming_to_completed_directly(host_user):
    now = timezone.now()
    tournament = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=10),
        tournament_end=now - timedelta(hours=1),
    )
    result = update_tournament_statuses()
    tournament.refresh_from_db()
    assert tournament.status == "completed"
    assert result["updated_ongoing"] == 0
    assert result["updated_completed"] == 1


@pytest.mark.django_db
def test_no_update_when_already_correct_status(host_user):
    now = timezone.now()
    upcoming_tournament = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now + timedelta(hours=5),
        tournament_end=now + timedelta(hours=10),
    )
    ongoing_tournament = TournamentFactory(
        host=host_user.host_profile,
        status="ongoing",
        tournament_start=now - timedelta(hours=1),
        tournament_end=now + timedelta(hours=5),
    )
    completed_tournament = TournamentFactory(
        host=host_user.host_profile,
        status="completed",
        tournament_start=now - timedelta(hours=10),
        tournament_end=now - timedelta(hours=1),
    )

    result = update_tournament_statuses()
    upcoming_tournament.refresh_from_db()
    ongoing_tournament.refresh_from_db()
    completed_tournament.refresh_from_db()
    assert upcoming_tournament.status == "upcoming"
    assert ongoing_tournament.status == "ongoing"
    assert completed_tournament.status == "completed"
    assert result["updated_ongoing"] == 0
    assert result["updated_completed"] == 0


@pytest.mark.django_db
def test_update_ongoing_to_completed(host_user):
    """Test that ongoing tournaments are updated to completed when end time passes"""
    now = timezone.now()
    tournament = TournamentFactory(
        host=host_user.host_profile,
        status="ongoing",
        tournament_start=now - timedelta(hours=10),
        tournament_end=now - timedelta(hours=1),
    )
    result = update_tournament_statuses()
    tournament.refresh_from_db()
    assert tournament.status == "completed"
    assert result["updated_ongoing"] == 0
    assert result["updated_completed"] == 1


@pytest.mark.django_db
def test_update_multiple_tournaments(host_user):
    """Test that multiple tournaments are updated correctly"""
    now = timezone.now()
    upcoming_to_ongoing = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=1),
        tournament_end=now + timedelta(hours=5),
    )
    ongoing_to_completed = TournamentFactory(
        host=host_user.host_profile,
        status="ongoing",
        tournament_start=now - timedelta(hours=10),
        tournament_end=now - timedelta(hours=1),
    )
    upcoming_to_completed = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=8),
        tournament_end=now - timedelta(hours=2),
    )
    result = update_tournament_statuses()
    upcoming_to_ongoing.refresh_from_db()
    ongoing_to_completed.refresh_from_db()
    upcoming_to_completed.refresh_from_db()
    assert upcoming_to_ongoing.status == "ongoing"
    assert ongoing_to_completed.status == "completed"
    assert upcoming_to_completed.status == "completed"
    assert result["updated_ongoing"] == 1
    assert result["updated_completed"] == 2


@pytest.mark.django_db
def test_cache_cleared_when_updates_occur(host_user):
    """Test that cache is cleared when tournaments are updated"""
    now = timezone.now()
    cache.set("tournaments:list:all", {"test": "data"}, timeout=300)
    assert cache.get("tournaments:list:all") is not None
    TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=1),
        tournament_end=now + timedelta(hours=5),
    )
    update_tournament_statuses()
    assert cache.get("tournaments:list:all") is None


@pytest.mark.django_db
def test_cache_not_cleared_when_no_updates(host_user):
    """Test that cache is not cleared when no tournaments are updated"""
    now = timezone.now()
    cache.set("tournaments:list:all", {"test": "data"}, timeout=300)
    assert cache.get("tournaments:list:all") is not None
    TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now + timedelta(hours=5),
        tournament_end=now + timedelta(hours=10),
    )
    update_tournament_statuses()
    assert cache.get("tournaments:list:all") is not None


@pytest.mark.django_db
def test_task_return_value_structure(host_user):
    now = timezone.now()
    TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now - timedelta(hours=1),
        tournament_end=now + timedelta(hours=5),
    )
    result = update_tournament_statuses()
    assert isinstance(result, dict)
    assert "updated_ongoing" in result
    assert "updated_completed" in result
    assert "timestamp" in result
    assert isinstance(result["updated_ongoing"], int)
    assert isinstance(result["updated_completed"], int)
    assert isinstance(result["timestamp"], str)


@pytest.mark.django_db
def test_edge_case_exact_start_time(host_user):
    now = timezone.now()
    tournament = TournamentFactory(
        host=host_user.host_profile,
        status="upcoming",
        tournament_start=now,
        tournament_end=now + timedelta(hours=6),
    )
    result = update_tournament_statuses()
    tournament.refresh_from_db()
    assert tournament.status == "ongoing"
    assert result["updated_ongoing"] == 1


@pytest.mark.django_db
def test_edge_case_exact_end_time(host_user):
    now = timezone.now()
    tournament = TournamentFactory(
        host=host_user.host_profile,
        status="ongoing",
        tournament_start=now - timedelta(hours=6),
        tournament_end=now,
    )
    result = update_tournament_statuses()
    tournament.refresh_from_db()
    assert tournament.status == "completed"
    assert result["updated_completed"] == 1
