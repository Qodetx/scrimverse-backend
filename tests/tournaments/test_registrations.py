"""
Test cases for Tournament and Scrim Registrations with Payment Gateway Mocking
"""
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from payments.models import Payment
from tests.factories import PlayerProfileFactory, UserFactory
from tournaments.models import TournamentRegistration

# Tournament Registration Tests with Payment


@pytest.mark.django_db
def test_player_register_for_free_tournament(authenticated_client, tournament, player_user, test_players):
    """Test player can register for free tournament (entry_fee = 0)"""
    # Set tournament as free
    tournament.entry_fee = Decimal("0.00")
    tournament.save()

    data = {
        "team_name": "Team Alpha",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
    }

    response = authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert TournamentRegistration.objects.filter(tournament=tournament).exists()

    # Check participant count increased
    tournament.refresh_from_db()
    assert tournament.current_participants == 1

    # Verify registration is confirmed (no payment required)
    registration = TournamentRegistration.objects.get(tournament=tournament, player=player_user.player_profile)
    assert registration.payment_status is True


@pytest.mark.django_db
def test_player_register_for_paid_tournament_initiates_payment(
    authenticated_client, tournament, player_user, test_players, mock_phonepe_initiate_payment
):
    """Test player registration for paid tournament initiates payment"""
    # Set tournament with entry fee
    tournament.entry_fee = Decimal("50.00")
    tournament.save()

    data = {
        "team_name": "Team Beta",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
    }

    response = authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    # Should return 200 with payment_required flag
    assert response.status_code == status.HTTP_200_OK
    # payment_required comes as ErrorDetail, so check string value
    payment_required = response.data.get("payment_required")
    assert payment_required is True or str(payment_required) == "True"
    assert "redirect_url" in response.data
    assert "merchant_order_id" in response.data

    # Verify PhonePe was called
    mock_phonepe_initiate_payment.assert_called_once()

    # Verify Payment record was created
    assert Payment.objects.filter(user=player_user, tournament=tournament, status="pending").exists()

    # Registration should NOT be created yet (pending payment)
    assert not TournamentRegistration.objects.filter(tournament=tournament, player=player_user.player_profile).exists()


@pytest.mark.django_db
def test_register_without_in_game_details_succeeds(authenticated_client, tournament, player_user, test_players):
    """Test registration succeeds without in_game_details (uses default empty dict)"""
    tournament.entry_fee = Decimal("0.00")
    tournament.save()

    data = {
        "team_name": "Team Delta",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ]
        # Missing in_game_details - should use default from model (empty dict)
    }
    response = authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    # With default dict for in_game_details, registration succeeds
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_twice_fails(api_client, tournament, test_players):
    """Test player cannot register for same tournament twice"""
    tournament.entry_fee = Decimal("0.00")
    tournament.save()

    # Create a player and register them
    player_user = UserFactory(user_type="player")
    PlayerProfileFactory(user=player_user)

    client = APIClient()
    client.force_authenticate(user=player_user)

    data = {
        "team_name": "First Team",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
    }
    # First registration should succeed
    response1 = client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")
    assert response1.status_code == status.HTTP_201_CREATED

    # Second registration should fail
    data2 = {
        "team_name": "Second Team",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
    }
    response2 = client.post(f"/api/tournaments/{tournament.id}/register/", data2, format="json")
    assert response2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_host_cannot_register_for_tournament(host_authenticated_client, tournament):
    """Test host cannot register for tournament"""
    data = {"team_name": "Host Team", "player_usernames": ["Host1"]}
    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_unauthenticated_cannot_register(api_client, tournament):
    """Test unauthenticated user cannot register"""
    data = {"team_name": "Team", "player_usernames": ["Player"]}
    response = api_client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# Player Registrations Tests


@pytest.mark.django_db
def test_get_player_tournament_registrations(authenticated_client, tournament_registration):
    """Test getting player's tournament registrations"""
    response = authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) == 1
    assert results[0]["tournament"]["id"] == tournament_registration.tournament.id


@pytest.mark.django_db
def test_get_registrations_unauthenticated(api_client):
    """Test getting registrations without authentication"""
    response = api_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_host_cannot_get_registrations(host_authenticated_client):
    """Test host cannot access player registrations endpoint"""
    response = host_authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_empty_registrations(authenticated_client):
    """Test getting empty registrations list"""
    response = authenticated_client.get("/api/tournaments/my-registrations/")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) == 0


# Multiple Player Registration Tests


@pytest.mark.django_db
def test_multiple_players_register_free_tournament(tournament, test_players):
    """Test multiple players can register for same free tournament"""
    # Set as free tournament
    tournament.entry_fee = Decimal("0.00")
    tournament.save()

    # Create 3 teams with unique players for each team
    from tests.factories import PlayerProfileFactory, UserFactory

    # Create 3 team leaders + 9 additional teammates (3 per team)
    all_players = []
    for i in range(12):  # 3 teams * 4 players each
        user = UserFactory(user_type="player", username=f"squadplayer{i}")
        PlayerProfileFactory(user=user)
        all_players.append(user)

    # Register 3 teams with completely unique players
    for team_idx in range(3):
        # Get 4 unique players for this team
        team_start = team_idx * 4
        team_members = all_players[team_start : team_start + 4]

        client = APIClient()
        client.force_authenticate(user=team_members[0])  # First player is the leader

        data = {
            "team_name": f"Team {team_idx}",
            "player_usernames": [p.username for p in team_members],
        }
        response = client.post(f"/api/tournaments/{tournament.id}/register/", data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    tournament.refresh_from_db()
    assert tournament.current_participants == 3
    assert TournamentRegistration.objects.filter(tournament=tournament).count() == 3
