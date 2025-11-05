"""
Pytest fixtures and configuration for Scrimverse tests
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache

import pytest
from rest_framework.test import APIClient

from tests.factories import (
    HostProfileFactory,
    PlayerProfileFactory,
    ScrimFactory,
    ScrimRegistrationFactory,
    TournamentFactory,
    TournamentRegistrationFactory,
    UserFactory,
)

User = get_user_model()


# Check if Redis is available
def redis_available():
    """Check if Redis server is running"""
    try:
        from django.conf import settings

        import redis

        # Try to connect to Redis
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            socket_connect_timeout=1,
        )
        r.ping()
        return True
    except (redis.ConnectionError, redis.TimeoutError):
        return False


# Pytest marker for Redis-dependent tests
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "redis_required: mark test as requiring Redis server")


# Skip Redis tests if Redis is not available
def pytest_collection_modifyitems(config, items):
    """Skip Redis tests if Redis is not running"""
    if not redis_available():
        skip_redis = pytest.mark.skip(reason="Redis server not available (run 'redis-server' to enable cache tests)")
        for item in items:
            if "cache" in item.keywords or "redis_required" in item.keywords:
                item.add_marker(skip_redis)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Redis cache before and after each test"""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    """Return DRF API client"""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, player_user):
    """Return authenticated API client with player user"""
    api_client.force_authenticate(user=player_user)
    return api_client


@pytest.fixture
def host_authenticated_client(api_client, host_user):
    """Return authenticated API client with host user"""
    api_client.force_authenticate(user=host_user)
    return api_client


@pytest.fixture
def player_user(db):
    """Create a player user"""
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    return user


@pytest.fixture
def host_user(db):
    """Create a host user"""
    user = UserFactory(user_type="host")
    HostProfileFactory(user=user)
    return user


@pytest.fixture
def admin_user(db):
    """Create an admin user"""
    return User.objects.create_superuser(email="admin@test.com", username="admin", password="admin123")


@pytest.fixture
def multiple_players(db):
    """Create multiple player users"""
    players = []
    for i in range(5):
        user = UserFactory(user_type="player", username=f"player{i}")
        PlayerProfileFactory(user=user)
        players.append(user)
    return players


@pytest.fixture
def multiple_hosts(db):
    """Create multiple host users"""
    hosts = []
    for i in range(3):
        user = UserFactory(user_type="host", username=f"host{i}")
        HostProfileFactory(user=user)
        hosts.append(user)
    return hosts


@pytest.fixture
def tournament(db, host_user):
    """Create a tournament"""
    return TournamentFactory(host=host_user.host_profile)


@pytest.fixture
def upcoming_tournament(db, host_user):
    """Create an upcoming tournament"""
    return TournamentFactory(host=host_user.host_profile, status="upcoming")


@pytest.fixture
def ongoing_tournament(db, host_user):
    """Create an ongoing tournament"""
    return TournamentFactory(host=host_user.host_profile, status="ongoing")


@pytest.fixture
def completed_tournament(db, host_user):
    """Create a completed tournament"""
    return TournamentFactory(host=host_user.host_profile, status="completed")


@pytest.fixture
def multiple_tournaments(db, host_user):
    """Create multiple tournaments"""
    return [
        TournamentFactory(host=host_user.host_profile, status="upcoming"),
        TournamentFactory(host=host_user.host_profile, status="ongoing"),
        TournamentFactory(host=host_user.host_profile, status="completed"),
    ]


@pytest.fixture
def scrim(db, host_user):
    """Create a scrim"""
    return ScrimFactory(host=host_user.host_profile)


@pytest.fixture
def multiple_scrims(db, host_user):
    """Create multiple scrims"""
    return [
        ScrimFactory(host=host_user.host_profile, status="upcoming"),
        ScrimFactory(host=host_user.host_profile, status="ongoing"),
        ScrimFactory(host=host_user.host_profile, status="completed"),
    ]


@pytest.fixture
def tournament_registration(db, tournament, player_user):
    """Create a tournament registration"""
    return TournamentRegistrationFactory(tournament=tournament, player=player_user.player_profile)


@pytest.fixture
def scrim_registration(db, scrim, player_user):
    """Create a scrim registration"""
    return ScrimRegistrationFactory(scrim=scrim, player=player_user.player_profile)
