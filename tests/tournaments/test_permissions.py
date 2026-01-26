"""
Test cases for permissions and authorization
"""
from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import HostProfileFactory, TournamentFactory, TournamentRegistrationFactory, UserFactory

# Player Permission Tests


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_can_register_for_tournament(authenticated_client, tournament, player_user, test_players):
    """Test player can register for tournament"""
    # Set tournament as free to avoid payment
    tournament.entry_fee = 0
    tournament.save()

    data = {
        "team_name": "Player Team",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
        "in_game_details": {"ign": "Player", "uid": "UID"},
    }

    response = authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_can_view_own_registrations(authenticated_client):
    """Test player can view their registrations"""
    response = authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_cannot_create_tournament(authenticated_client):
    """Test player cannot create tournament"""
    data = {"title": "Unauthorized Tournament"}
    response = authenticated_client.post("/api/tournaments/create/", data)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_cannot_update_tournament(authenticated_client, tournament):
    """Test player cannot update tournament"""
    data = {"title": "Updated by Player"}
    response = authenticated_client.patch(f"/api/tournaments/{tournament.id}/update/", data)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_cannot_delete_tournament(authenticated_client, tournament):
    """Test player cannot delete tournament"""
    response = authenticated_client.delete(f"/api/tournaments/{tournament.id}/delete/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.permissions
@pytest.mark.django_db
def test_player_can_rate_host(authenticated_client, host_user):
    """Test player can rate a host"""
    data = {"rating": 5, "review": "Great host!"}
    response = authenticated_client.post(f"/api/tournaments/host/{host_user.host_profile.id}/rate/", data)

    assert response.status_code == status.HTTP_201_CREATED


# Host Permission Tests


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_can_create_tournament(host_authenticated_client):
    """Test host can create tournament"""

    now = timezone.now()
    data = {
        "title": "Host Tournament",
        "description": "Test",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 100,
        "entry_fee": "0.00",  # Free to avoid payment
        "prize_pool": "0.00",
        "registration_start": now.isoformat(),
        "registration_end": (now + timedelta(days=5)).isoformat(),
        "tournament_start": (now + timedelta(days=6)).isoformat(),
        "tournament_end": (now + timedelta(days=6, hours=6)).isoformat(),
        "rules": "Rules",
    }
    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_200_OK  # Free plan returns 200


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_can_update_own_tournament(host_authenticated_client, tournament):
    """Test host can update their own tournament"""
    data = {"title": "Host Updated Title"}
    response = host_authenticated_client.patch(f"/api/tournaments/{tournament.id}/update/", data, format="json")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_can_delete_own_tournament(host_authenticated_client, tournament):
    """Test host can delete their own tournament"""
    response = host_authenticated_client.delete(f"/api/tournaments/{tournament.id}/delete/")

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_cannot_register_for_tournament(host_authenticated_client, tournament):
    """Test host cannot register as player"""
    data = {"team_name": "Host Team", "team_members": ["Host"], "in_game_details": {"ign": "Host", "uid": "UID"}}
    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_cannot_view_player_registrations(host_authenticated_client):
    """Test host cannot access player-only endpoints"""
    response = host_authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_cannot_rate_another_host(host_authenticated_client, host_user):
    """Test host cannot rate other hosts"""
    data = {"rating": 5, "review": "Nice host"}
    response = host_authenticated_client.post(f"/api/tournaments/host/{host_user.host_profile.id}/rate/", data)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# Guest Permission Tests


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_can_view_tournament_list(api_client, tournament):
    """Test guest can view tournament list"""
    response = api_client.get("/api/tournaments/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_can_view_tournament_detail(api_client, tournament):
    """Test guest can view tournament details"""
    response = api_client.get(f"/api/tournaments/{tournament.id}/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_can_view_host_tournaments(api_client, host_user, tournament):
    """Test guest can view tournaments by host"""
    response = api_client.get(f"/api/tournaments/host/{host_user.host_profile.id}/")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_cannot_create_tournament(api_client):
    """Test guest cannot create tournament"""
    data = {"title": "Guest Tournament"}
    response = api_client.post("/api/tournaments/create/", data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_cannot_register_for_tournament(api_client, tournament):
    """Test guest cannot register for tournament"""
    data = {"team_name": "Guest Team", "team_members": ["Guest"], "in_game_details": {"ign": "Guest", "uid": "UID"}}
    response = api_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_cannot_view_registrations(api_client):
    """Test guest cannot view player registrations"""
    response = api_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.permissions
@pytest.mark.django_db
def test_guest_can_view_host_ratings(api_client, host_user):
    """Test guest can view host ratings"""
    response = api_client.get(f"/api/tournaments/host/{host_user.host_profile.id}/ratings/")

    assert response.status_code == status.HTTP_200_OK


# Cross-User Permission Tests


@pytest.mark.permissions
@pytest.mark.django_db
def test_host_cannot_update_other_host_tournament(host_user):
    """Test host cannot update another host's tournament"""

    # Create second host
    host2_user = UserFactory(user_type="host")
    host2_profile = HostProfileFactory(user=host2_user)
    tournament = TournamentFactory(host=host2_profile)

    # First host tries to update
    client = APIClient()
    client.force_authenticate(user=host_user)

    data = {"title": "Hacked"}
    response = client.patch(f"/api/tournaments/{tournament.id}/update/", data)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.permissions
@pytest.mark.django_db
def test_players_have_separate_registrations(tournament, multiple_players):
    """Test players can only see their own registrations"""

    # Register multiple players
    for player in multiple_players[:2]:
        TournamentRegistrationFactory(tournament=tournament, player=player.player_profile)

    # First player checks registrations
    client1 = APIClient()
    client1.force_authenticate(user=multiple_players[0])
    response1 = client1.get("/api/tournaments/my-registrations/")

    # Second player checks registrations
    client2 = APIClient()
    client2.force_authenticate(user=multiple_players[1])
    response2 = client2.get("/api/tournaments/my-registrations/")

    assert response1.status_code == status.HTTP_200_OK
    assert response2.status_code == status.HTTP_200_OK

    # Each should only see their own registration
    results1 = response1.data.get("results", response1.data)
    results2 = response2.data.get("results", response2.data)
    assert len(results1) == 1
    assert len(results2) == 1

    # Verify they see different registrations
    assert results1[0]["player"]["id"] == multiple_players[0].player_profile.id
    assert results2[0]["player"]["id"] == multiple_players[1].player_profile.id
