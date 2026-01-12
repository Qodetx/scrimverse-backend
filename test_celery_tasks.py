"""
Celery Tasks Testing
Tests for all implemented Celery tasks
"""
import pytest

from accounts.tasks import update_host_rating_cache
from tests.factories import HostProfileFactory
from tournaments.tasks import update_host_dashboard_stats, update_platform_statistics


@pytest.mark.django_db
def test_platform_statistics():
    """Test platform statistics calculation"""
    result = update_platform_statistics()
    assert result is not None
    assert "error" not in result or result.get("total_tournaments") is not None


@pytest.mark.django_db
def test_host_dashboard_stats():
    """Test host dashboard statistics"""
    # Create a host for testing
    host = HostProfileFactory()

    result = update_host_dashboard_stats(host.id)

    assert result is not None
    assert "error" not in result or result.get("total_tournaments") is not None


@pytest.mark.django_db
def test_host_rating_cache():
    """Test host rating cache"""
    # Create a host for testing
    host = HostProfileFactory()

    result = update_host_rating_cache(host.id)

    assert result is not None
    assert "error" not in result or result.get("average_rating") is not None


@pytest.mark.django_db
def test_all_tasks():
    """Test that all critical tasks can be imported and called"""
    # Create test data
    host = HostProfileFactory()

    # Test platform stats
    platform_result = update_platform_statistics()
    assert platform_result is not None

    # Test host dashboard
    dashboard_result = update_host_dashboard_stats(host.id)
    assert dashboard_result is not None

    # Test host rating
    rating_result = update_host_rating_cache(host.id)
    assert rating_result is not None
