"""
Tests for tournament advanced filtering
"""
from decimal import Decimal

from django.core.cache import cache

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import TournamentFactory
from tournaments.models import Tournament


def get_results(data):
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


@pytest.mark.django_db
def test_filter_tournaments_by_game_name():
    """Test filtering tournaments by game name (icontains)"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(game_name="BGMI - Pro League")
    TournamentFactory(game_name="COD Champions")
    TournamentFactory(game_name="BGMI Scrims")

    response = client.get("/api/tournaments/", {"game": "BGMI"})
    assert response.status_code == status.HTTP_200_OK

    results = get_results(response.data)
    assert len(results) == 2
    for item in results:
        assert "BGMI" in item["game_name"]


@pytest.mark.django_db
def test_filter_tournaments_by_status():
    """Test filtering tournaments by status"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(status="upcoming")
    TournamentFactory(status="ongoing")
    TournamentFactory(status="completed")

    response = client.get("/api/tournaments/", {"status": "upcoming"})
    assert response.status_code == status.HTTP_200_OK
    results = get_results(response.data)
    assert len(results) == 1
    assert results[0]["status"] == "upcoming"


@pytest.mark.django_db
def test_filter_tournaments_by_event_mode():
    """Test filtering tournaments by event mode"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(event_mode="TOURNAMENT")
    TournamentFactory(event_mode="SCRIM")

    response = client.get("/api/tournaments/", {"event_mode": "SCRIM"})
    assert response.status_code == status.HTTP_200_OK
    results = get_results(response.data)
    assert len(results) == 1
    assert results[0]["event_mode"] == "SCRIM"


@pytest.mark.django_db
def test_filter_tournaments_by_entry_fee():
    """Test filtering tournaments by exact entry fee"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(entry_fee=0)
    TournamentFactory(entry_fee=100)

    response = client.get("/api/tournaments/", {"entry_fee": "0.00"})
    assert response.status_code == status.HTTP_200_OK
    results = get_results(response.data)
    assert len(results) == 1
    assert Decimal(results[0]["entry_fee"]) == Decimal("0.00")


@pytest.mark.django_db
def test_filter_tournaments_by_category_official():
    """Test filtering tournaments by category 'official' (featured/premium)"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(plan_type="basic")
    TournamentFactory(plan_type="featured")
    TournamentFactory(plan_type="premium")

    response = client.get("/api/tournaments/", {"category": "official"})
    assert response.status_code == status.HTTP_200_OK
    results = get_results(response.data)
    assert len(results) == 2
    for item in results:
        assert item["plan_type"] in ["featured", "premium"]


@pytest.mark.django_db
def test_filter_tournaments_by_category_all():
    """Test filtering tournaments by category 'all' (basic)"""
    Tournament.objects.all().delete()
    cache.clear()

    client = APIClient()
    TournamentFactory(plan_type="basic")
    TournamentFactory(plan_type="featured")

    response = client.get("/api/tournaments/", {"category": "all"})
    assert response.status_code == status.HTTP_200_OK
    results = get_results(response.data)
    assert len(results) == 1
    assert results[0]["plan_type"] == "basic"
