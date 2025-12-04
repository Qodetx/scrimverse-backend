"""
Test cases for Platform Stats API
"""
import pytest
from rest_framework import status

from tests.factories import PlayerProfileFactory, TournamentFactory, TournamentRegistrationFactory, UserFactory


@pytest.mark.django_db
def test_platform_stats_returns_correct_data(api_client, tournament, player_user):
    """Test platform stats API returns correct aggregated data"""
    # Create some additional data
    # 2 more tournaments (total 3)
    TournamentFactory(host=tournament.host, status="upcoming", prize_pool="1000.00")
    TournamentFactory(host=tournament.host, status="completed", prize_pool="5000.00")

    # Create additional players (total 2 including player_user)
    player2 = UserFactory(user_type="player")
    PlayerProfileFactory(user=player2)

    # Create registrations (total 2)
    TournamentRegistrationFactory(tournament=tournament, player=player_user.player_profile)
    TournamentRegistrationFactory(tournament=tournament, player=player2.player_profile)

    response = api_client.get("/api/tournaments/stats/platform/")

    assert response.status_code == status.HTTP_200_OK
    assert "total_tournaments" in response.data
    assert "total_players" in response.data
    assert "total_prize_money" in response.data
    assert "total_registrations" in response.data

    # Verify counts
    assert response.data["total_tournaments"] == 3
    assert response.data["total_players"] == 2
    assert response.data["total_registrations"] == 2


@pytest.mark.django_db
def test_platform_stats_prize_money_only_completed(api_client, host_user):
    """Test that prize money only counts completed tournaments"""
    # Create tournaments with different statuses
    TournamentFactory(host=host_user.host_profile, status="upcoming", prize_pool="1000.00")
    TournamentFactory(host=host_user.host_profile, status="ongoing", prize_pool="2000.00")
    TournamentFactory(host=host_user.host_profile, status="completed", prize_pool="3000.00")
    TournamentFactory(host=host_user.host_profile, status="completed", prize_pool="4000.00")

    response = api_client.get("/api/tournaments/stats/platform/")

    assert response.status_code == status.HTTP_200_OK
    # Only completed tournaments: 3000 + 4000 = 7000
    assert response.data["total_prize_money"] == "7000.00"


@pytest.mark.django_db
def test_platform_stats_empty_database(api_client):
    """Test platform stats with no data"""
    response = api_client.get("/api/tournaments/stats/platform/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_tournaments"] == 0
    assert response.data["total_players"] == 0
    assert response.data["total_prize_money"] == "0"
    assert response.data["total_registrations"] == 0


@pytest.mark.django_db
def test_platform_stats_no_authentication_required(api_client, tournament):
    """Test that platform stats endpoint doesn't require authentication"""
    # Unauthenticated request should work
    response = api_client.get("/api/tournaments/stats/platform/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_platform_stats_counts_all_tournaments(api_client, host_user):
    """Test that all tournaments are counted regardless of status"""
    TournamentFactory(host=host_user.host_profile, status="upcoming")
    TournamentFactory(host=host_user.host_profile, status="ongoing")
    TournamentFactory(host=host_user.host_profile, status="completed")
    TournamentFactory(host=host_user.host_profile, status="cancelled")

    response = api_client.get("/api/tournaments/stats/platform/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_tournaments"] == 4
