"""
Tests for tournament finalization and winner selection
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    HostProfileFactory,
    PlayerProfileFactory,
    TeamFactory,
    TournamentFactory,
    TournamentRegistrationFactory,
)


@pytest.mark.django_db
def test_select_winner_final_round():
    """Test selecting a winner for the final round of a tournament"""
    host_profile = HostProfileFactory()
    host_user = host_profile.user

    # 1. Setup tournament with 2 rounds
    tournament = TournamentFactory(
        host=host_profile,
        current_round=2,
        rounds=[
            {"round": 1, "max_teams": 4, "qualifying_teams": 2},
            {"round": 2, "max_teams": 2, "qualifying_teams": 0},  # 0 means final
        ],
    )

    # 2. Setup registrations
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    # 3. Simulate round 1 selection
    tournament.selected_teams = {"1": [reg1.id, reg2.id]}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host_user)

    response = client.post(f"/api/tournaments/{tournament.id}/select-winner/", {"winner_id": reg1.id})

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.winners["2"] == reg1.id
    assert response.data["winner"]["id"] == reg1.id


@pytest.mark.django_db
def test_end_tournament_updates_player_wins():
    """Test that individual player total_wins is updated when tournament is finalized"""
    from tournaments.tasks import update_leaderboard

    host_profile = HostProfileFactory()

    p1_profile = PlayerProfileFactory()
    p2_profile = PlayerProfileFactory()

    # 1. Setup teams
    team1 = TeamFactory(is_temporary=False)
    team2 = TeamFactory(is_temporary=False)

    # 2. Setup completed tournament with winner
    tournament = TournamentFactory(
        host=host_profile,
        status="completed",
        current_round=0,
        rounds=[{"round": 1, "max_teams": 2, "qualifying_teams": 0}],
    )

    reg1 = TournamentRegistrationFactory(tournament=tournament, team=team1, player=p1_profile, status="confirmed")
    TournamentRegistrationFactory(tournament=tournament, team=team2, player=p2_profile, status="confirmed")

    tournament.winners = {"1": reg1.id}
    tournament.save()

    # Manually run update_leaderboard
    update_leaderboard()

    p1_profile.refresh_from_db()
    p2_profile.refresh_from_db()

    # We expect p1_profile.total_wins to be 1
    assert p1_profile.total_wins == 1
    assert p2_profile.total_wins == 0


@pytest.mark.django_db
def test_end_tournament_updates_player_participation():
    """Test that player total_tournaments_participated is updated"""
    from tournaments.tasks import update_leaderboard

    host_profile = HostProfileFactory()
    p1_profile = PlayerProfileFactory()

    tournament = TournamentFactory(host=host_profile, status="completed")
    TournamentRegistrationFactory(tournament=tournament, player=p1_profile, status="confirmed")

    update_leaderboard()

    p1_profile.refresh_from_db()
    assert p1_profile.total_tournaments_participated == 1
