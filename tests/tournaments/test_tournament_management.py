"""
Test cases for Tournament Management features
- Round management (start round, select teams, end round)
- Winner selection for final rounds
- Update tournament fields (restricted)
- End tournament
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    HostProfileFactory,
    PlayerProfileFactory,
    TournamentFactory,
    TournamentRegistrationFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_get_manage_tournament_as_host(host_authenticated_client, tournament):
    """Test host can get tournament management data"""
    response = host_authenticated_client.get(f"/api/tournaments/{tournament.id}/manage/")

    assert response.status_code == status.HTTP_200_OK
    assert "tournament" in response.data
    assert "registrations" in response.data
    assert response.data["tournament"]["id"] == tournament.id


@pytest.mark.django_db
def test_get_manage_tournament_as_player_forbidden(authenticated_client, tournament):
    """Test player cannot access tournament management"""
    response = authenticated_client.get(f"/api/tournaments/{tournament.id}/manage/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_get_manage_tournament_other_host_forbidden(host_user, tournament):
    """Test host cannot access other host's tournament management"""
    other_host_user = UserFactory(user_type="host")
    HostProfileFactory(user=other_host_user)  # Create host profile for other host
    client = APIClient()
    client.force_authenticate(user=other_host_user)

    response = client.get(f"/api/tournaments/{tournament.id}/manage/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_start_round_1(host_authenticated_client, tournament):
    """Test starting round 1"""
    tournament.status = "ongoing"
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/start-round/1/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.current_round == 1
    assert tournament.round_status["1"] == "ongoing"


@pytest.mark.django_db
def test_start_round_2_before_round_1_completed_fails(host_authenticated_client, tournament):
    """Test cannot start round 2 before round 1 is completed"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/start-round/2/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "must be completed" in response.data["error"].lower()


@pytest.mark.django_db
def test_start_round_2_after_round_1_completed(host_authenticated_client, tournament):
    """Test starting round 2 after round 1 is completed"""
    tournament.status = "ongoing"
    tournament.round_status = {"1": "completed"}
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/start-round/2/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.current_round == 2
    assert tournament.round_status["2"] == "ongoing"


@pytest.mark.django_db
def test_select_teams_for_round(host_authenticated_client, tournament):
    """Test selecting teams for current round"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.selected_teams = {}
    tournament.save()

    # Create registrations
    player1 = PlayerProfileFactory()
    player2 = PlayerProfileFactory()
    reg1 = TournamentRegistrationFactory(tournament=tournament, player=player1, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, player=player2, status="confirmed")

    data = {"action": "select", "team_ids": [reg1.id, reg2.id]}

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/select-teams/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert len(tournament.selected_teams["1"]) == 2
    assert reg1.id in tournament.selected_teams["1"]
    assert reg2.id in tournament.selected_teams["1"]


@pytest.mark.django_db
def test_select_teams_exceeds_qualifying_limit_fails(host_authenticated_client, tournament):
    """Test selecting more teams than qualifying limit fails"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.selected_teams = {}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]
    tournament.save()

    # Create registrations
    regs = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(3)]

    data = {"action": "select", "team_ids": [reg.id for reg in regs]}

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/select-teams/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "more than" in response.data["error"].lower()


@pytest.mark.django_db
def test_end_round_with_correct_team_count(host_authenticated_client, tournament):
    """Test ending round with correct number of teams selected"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]

    # Create and select 2 teams
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.round_status["1"] == "completed"
    # Should auto-advance to round 2 if exists
    if len(tournament.rounds) > 1:
        assert tournament.current_round == 2


@pytest.mark.django_db
def test_end_round_with_incorrect_team_count_fails(host_authenticated_client, tournament):
    """Test ending round with incorrect number of teams fails"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]
    tournament.selected_teams = {"1": [1]}  # Only 1 team selected, need 2
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "exactly" in response.data["error"].lower()


@pytest.mark.django_db
def test_end_round_auto_advances_to_next_round(host_authenticated_client):
    """Test ending round automatically advances to next round"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    response = client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.round_status["1"] == "completed"
    assert tournament.current_round == 2
    assert tournament.round_status["2"] == "ongoing"


@pytest.mark.django_db
def test_select_winner_final_round(host_authenticated_client):
    """Test selecting winner for final round"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[
            {"round": 1, "max_teams": 4, "qualifying_teams": 2},
            {"round": 2, "max_teams": 2},  # Final round, no qualifying_teams
        ],
    )

    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    # Set Round 1 selected teams as these are the participants for Round 2
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    data = {"winner_id": reg1.id}
    response = client.post(f"/api/tournaments/{tournament.id}/select-winner/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.winners["2"] == reg1.id
    assert "winner" in response.data


@pytest.mark.django_db
def test_select_winner_non_final_round_fails(host_authenticated_client, tournament):
    """Test selecting winner for non-final round fails"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}
    tournament.save()

    data = {"winner_id": reg1.id}
    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/select-winner/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "final round" in response.data["error"].lower()


@pytest.mark.django_db
def test_select_winner_not_in_selected_teams_fails(host_authenticated_client):
    """Test selecting winner that's not in participating teams fails"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg3 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    # Round 1 selected teams (participants for Round 2)
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}  # reg3 is NOT here
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    data = {"winner_id": reg3.id}  # reg3 not in participating teams
    response = client.post(f"/api/tournaments/{tournament.id}/select-winner/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "participating teams" in response.data["error"].lower()


@pytest.mark.django_db
def test_end_final_round_without_winner_fails(host_authenticated_client):
    """Test ending final round without selecting winner fails"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"2": [reg1.id, reg2.id]}
    tournament.winners = {}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    response = client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "winner" in response.data["error"].lower()


@pytest.mark.django_db
def test_end_final_round_with_winner_succeeds(host_authenticated_client):
    """Test ending final round with winner selected succeeds"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"2": [reg1.id, reg2.id]}
    tournament.winners = {"2": reg1.id}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    response = client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.round_status["2"] == "completed"
    assert tournament.current_round == 0  # All rounds completed


@pytest.mark.django_db
def test_end_tournament_all_rounds_completed(host_authenticated_client):
    """Test ending tournament when all rounds are completed"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    tournament.round_status = {"1": "completed", "2": "completed"}
    tournament.current_round = 0
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    response = client.post(f"/api/tournaments/{tournament.id}/end/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.status == "completed"


@pytest.mark.django_db
def test_end_tournament_early_allowed(host_authenticated_client, tournament):
    """Test ending tournament early (before all rounds completed) is allowed"""
    tournament.status = "ongoing"
    tournament.round_status = {"1": "ongoing"}
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/end/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.status == "completed"


@pytest.mark.django_db
def test_update_tournament_fields_restricted(host_authenticated_client, tournament):
    """Test updating tournament fields with restrictions (only allowed fields)"""
    original_max_participants = tournament.max_participants
    original_game_name = tournament.game_name

    data = {
        "title": "Updated Title",
        "description": "Updated description",
        "rules": "Updated rules",
        "discord_id": "discord.gg/updated",
        # Try to update restricted fields
        "max_participants": 200,  # Should be ignored
        "game_name": "Valorant",  # Should be ignored
    }

    response = host_authenticated_client.patch(f"/api/tournaments/{tournament.id}/update-fields/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.title == "Updated Title"
    assert tournament.description == "Updated description"
    assert tournament.rules == "Updated rules"
    assert tournament.discord_id == "discord.gg/updated"
    # Restricted fields should not be updated (check original values)
    assert tournament.max_participants == original_max_participants
    assert tournament.game_name == original_game_name


@pytest.mark.django_db
def test_update_tournament_fields_as_player_forbidden(authenticated_client, tournament):
    """Test player cannot update tournament fields"""
    data = {"title": "Hacked Title"}
    response = authenticated_client.patch(f"/api/tournaments/{tournament.id}/update-fields/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_get_tournament_registrations_as_host(host_authenticated_client, tournament):
    """Test host can get tournament registrations"""
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="pending")

    response = host_authenticated_client.get(f"/api/tournaments/{tournament.id}/registrations/")

    assert response.status_code == status.HTTP_200_OK
    # Response might be a list or paginated
    registrations = response.data if isinstance(response.data, list) else response.data.get("results", [])
    assert len(registrations) >= 2
    registration_ids = [r["id"] for r in registrations]
    assert reg1.id in registration_ids
    assert reg2.id in registration_ids


@pytest.mark.django_db
def test_get_tournament_registrations_as_player_forbidden(authenticated_client, tournament):
    """Test player cannot get tournament registrations"""
    response = authenticated_client.get(f"/api/tournaments/{tournament.id}/registrations/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_select_teams_uses_qualifying_teams_not_max_teams(host_authenticated_client, tournament):
    """Test team selection uses qualifying_teams limit, not max_teams"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]
    tournament.selected_teams = {}
    tournament.save()

    # Create 4 registrations
    regs = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(4)]

    # Try to select 3 teams (more than qualifying_teams=2, but less than max_teams=4)
    data = {"action": "select", "team_ids": [regs[0].id, regs[1].id, regs[2].id]}

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/select-teams/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "more than 2" in response.data["error"] or "2 teams" in response.data["error"]


@pytest.mark.django_db
def test_end_round_uses_qualifying_teams_not_max_teams(host_authenticated_client, tournament):
    """Test ending round validates against qualifying_teams, not max_teams"""
    tournament.status = "ongoing"
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.rounds = [{"round": 1, "max_teams": 4, "qualifying_teams": 2}]

    # Select only 1 team (less than qualifying_teams=2)
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    tournament.selected_teams = {"1": [reg1.id]}
    tournament.save()

    response = host_authenticated_client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "exactly 2" in response.data["error"] or "2 teams" in response.data["error"]
