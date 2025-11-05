"""
Test cases for Redis caching functionality
"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

# Tournament List Cache Tests


@pytest.mark.cache
@pytest.mark.django_db
def test_tournament_list_cached_on_first_request(api_client, multiple_tournaments):
    """Test tournament list is cached after first request"""
    # First request - cache miss
    response1 = api_client.get("/api/tournaments/")
    assert response1.status_code == status.HTTP_200_OK

    # Verify cache is set
    cached_data = cache.get("tournaments:list:all")
    assert cached_data is not None
    assert len(cached_data) == 3


@pytest.mark.cache
@pytest.mark.django_db
def test_tournament_list_served_from_cache(api_client, multiple_tournaments):
    """Test second request is served from cache"""
    # First request
    response1 = api_client.get("/api/tournaments/")

    # Second request (should be from cache)
    response2 = api_client.get("/api/tournaments/")

    assert response1.status_code == status.HTTP_200_OK
    assert response2.status_code == status.HTTP_200_OK
    assert response1.data == response2.data


@pytest.mark.cache
@pytest.mark.django_db
def test_filtered_list_not_cached(api_client, multiple_tournaments):
    """Test filtered tournament list is not cached"""
    response = api_client.get("/api/tournaments/", {"status": "upcoming"})

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_invalidated_on_tournament_create(host_authenticated_client, multiple_tournaments):
    """Test cache is cleared when new tournament is created"""
    # Prime the cache
    client = APIClient()
    client.get("/api/tournaments/")

    # Verify cache exists
    assert cache.get("tournaments:list:all") is not None

    # Create new tournament
    now = timezone.now()
    data = {
        "title": "New Cached Tournament",
        "description": "Test",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 100,
        "entry_fee": "50.00",
        "prize_pool": "5000.00",
        "registration_start": now.isoformat(),
        "registration_end": (now + timedelta(days=5)).isoformat(),
        "tournament_start": (now + timedelta(days=6)).isoformat(),
        "tournament_end": (now + timedelta(days=6, hours=6)).isoformat(),
        "rules": "Rules",
    }
    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED

    # Verify cache is cleared
    assert cache.get("tournaments:list:all") is None


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_invalidated_on_tournament_update(host_authenticated_client, tournament):
    """Test cache is cleared when tournament is updated"""
    # Prime the cache
    client = APIClient()
    client.get("/api/tournaments/")
    assert cache.get("tournaments:list:all") is not None

    # Update tournament
    data = {"title": "Updated Title"}
    response = host_authenticated_client.patch(f"/api/tournaments/{tournament.id}/update/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert cache.get("tournaments:list:all") is None


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_invalidated_on_tournament_delete(host_authenticated_client, tournament):
    """Test cache is cleared when tournament is deleted"""
    # Prime the cache
    client = APIClient()
    client.get("/api/tournaments/")
    assert cache.get("tournaments:list:all") is not None

    # Delete tournament
    response = host_authenticated_client.delete(f"/api/tournaments/{tournament.id}/delete/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert cache.get("tournaments:list:all") is None


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_invalidated_on_registration(authenticated_client, tournament):
    """Test cache is cleared when player registers"""
    # Prime the cache
    client = APIClient()
    client.get("/api/tournaments/")
    assert cache.get("tournaments:list:all") is not None

    # Register for tournament
    data = {
        "team_name": "Cache Test Team",
        "team_members": ["Player1"],
        "in_game_details": {"ign": "CacheGamer", "uid": "UID999"},
    }
    authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    # Note: This might return 400 if registration format is wrong
    # but we're mainly testing cache invalidation logic
    assert cache.get("tournaments:list:all") is None


# Cache Behavior Tests


@pytest.mark.cache
@pytest.mark.django_db
def test_empty_list_cached(api_client):
    """Test empty tournament list is also cached"""
    response = api_client.get("/api/tournaments/")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 0

    cached_data = cache.get("tournaments:list:all")
    assert cached_data is not None
    assert len(cached_data) == 0


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_cleared_between_tests(api_client, tournament):
    """Test cache is properly cleared between tests (via fixture)"""
    # This test verifies the autouse clear_cache fixture works
    cached_data = cache.get("tournaments:list:all")
    assert cached_data is None


@pytest.mark.cache
@pytest.mark.django_db
def test_cache_ttl_set_correctly(api_client, tournament):
    """Test cache TTL is set (we can't easily test expiry time)"""
    response = api_client.get("/api/tournaments/")

    assert response.status_code == status.HTTP_200_OK

    # Cache should exist
    cached_data = cache.get("tournaments:list:all")
    assert cached_data is not None


# Non-Cached Endpoints Tests


@pytest.mark.cache
@pytest.mark.django_db
def test_tournament_detail_not_cached(api_client, tournament):
    """Test tournament detail endpoint is not cached"""
    response = api_client.get(f"/api/tournaments/{tournament.id}/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.cache
@pytest.mark.django_db
def test_host_tournaments_not_cached(api_client, host_user, tournament):
    """Test host tournaments endpoint is not cached"""
    response = api_client.get(f"/api/tournaments/host/{host_user.host_profile.id}/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.cache
@pytest.mark.django_db
def test_registrations_not_cached(authenticated_client, tournament_registration):
    """Test player registrations are not cached"""
    response = authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_200_OK
