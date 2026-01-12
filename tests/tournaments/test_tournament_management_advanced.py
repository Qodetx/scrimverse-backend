"""
Advanced tests for tournament management
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import HostProfileFactory, TournamentFactory, TournamentRegistrationFactory


@pytest.mark.django_db
def test_confirm_rejected_team_increases_count():
    """Test confirming a previously rejected team increases participant count"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    # 1. Setup tournament with 1 participant already
    tournament = TournamentFactory(host=host_profile, current_participants=1, max_participants=10)

    # 2. Setup a rejected registration
    reg = TournamentRegistrationFactory(tournament=tournament, status="rejected")

    client = APIClient()
    client.force_authenticate(user=host_user)

    response = client.patch(f"/api/tournaments/{tournament.id}/registrations/{reg.id}/status/", {"status": "confirmed"})

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.current_participants == 2
    reg.refresh_from_db()
    assert reg.status == "confirmed"


@pytest.mark.django_db
def test_reject_confirmed_team_decreases_count():
    """Test rejecting a confirmed team decreases participant count"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    tournament = TournamentFactory(host=host_profile, current_participants=5)
    reg = TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host_user)

    response = client.patch(f"/api/tournaments/{tournament.id}/registrations/{reg.id}/status/", {"status": "rejected"})

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.current_participants == 4
    reg.refresh_from_db()
    assert reg.status == "rejected"


@pytest.mark.django_db
def test_confirm_team_fails_if_tournament_full():
    """Test that confirming a team fails if tournament max_participants reached"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    tournament = TournamentFactory(host=host_profile, current_participants=2, max_participants=2)
    reg = TournamentRegistrationFactory(tournament=tournament, status="rejected")

    client = APIClient()
    client.force_authenticate(user=host_user)

    # Check current participants before
    assert tournament.current_participants == 2

    response = client.patch(f"/api/tournaments/{tournament.id}/registrations/{reg.id}/status/", {"status": "confirmed"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Tournament is full" in response.data["error"]
    tournament.refresh_from_db()
    assert tournament.current_participants == 2


@pytest.mark.django_db
def test_start_tournament():
    """Test host explicitly starting a tournament"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    tournament = TournamentFactory(host=host_profile, status="upcoming")
    # Add some pending registrations
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="pending")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="pending")

    client = APIClient()
    client.force_authenticate(user=host_user)

    response = client.post(f"/api/tournaments/{tournament.id}/start/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.status == "ongoing"
    assert tournament.current_round == 1

    # Check if pending registrations were confirmed
    reg1.refresh_from_db()
    reg2.refresh_from_db()
    assert reg1.status == "confirmed"
    assert reg2.status == "confirmed"


@pytest.mark.django_db
def test_host_dashboard_stats_view():
    """Test getting host dashboard data"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    # Create some tournaments and registrations
    t1 = TournamentFactory(host=host_profile, status="ongoing", title="Live Tourney")
    TournamentFactory(host=host_profile, status="upcoming", title="Upcoming Tourney")
    TournamentRegistrationFactory(tournament=t1, team_name="Team Alpha")

    client = APIClient()
    client.force_authenticate(user=host_user)

    # Correct URL is /api/tournaments/stats/host/
    response = client.get("/api/tournaments/stats/host/")

    assert response.status_code == status.HTTP_200_OK
    # Stats are within the 'stats' key
    assert response.data["stats"]["active_tournaments"] >= 1
    assert "live_tournaments" in response.data
    assert "recent_activity" in response.data
    # Check for recent activity - registration record
    found_activity = False
    for act in response.data["recent_activity"]:
        if act["type"] == "registration" and "Live Tourney" in act["message"]:
            found_activity = True
            break
    assert found_activity
