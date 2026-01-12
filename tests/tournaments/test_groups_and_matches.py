"""
Comprehensive test cases for Tournament Groups and Match Management
Tests cover:
- Round configuration and group division (even and uneven)
- Match score updates
- Room ID/Password display
- Points table updates
- Qualifying teams logic
- Next round advancing
- Round results and winner selection
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
from tournaments.models import Group, Match, MatchScore, RoundScore

# ============================================================================
# ROUND CONFIGURATION AND GROUP DIVISION TESTS
# ============================================================================


@pytest.mark.django_db
def test_configure_round_even_division(host_authenticated_client):
    """Test configuring round with even team division"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        event_mode="TOURNAMENT",
        rounds=[{"round": 1, "max_teams": 16, "qualifying_teams": 8}],
    )

    # Create 16 registrations
    for i in range(16):
        TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Configure round: 16 teams, 4 groups, 4 teams per group
    data = {"teams_per_group": 4, "qualifying_per_group": 2, "matches_per_group": 3}

    response = client.post(f"/api/tournaments/{tournament.id}/rounds/1/configure/", data, format="json")

    # API might return 200 OK or 201 CREATED depending on implementation
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]
    assert Group.objects.filter(tournament=tournament, round_number=1).count() == 4

    # Check each group has 4 teams
    for group in Group.objects.filter(tournament=tournament, round_number=1):
        assert group.teams.count() == 4
        assert group.matches.count() == 3


@pytest.mark.django_db
def test_configure_round_uneven_division(host_authenticated_client):
    """Test configuring round with uneven team division"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing", event_mode="TOURNAMENT")

    # Create 15 registrations (not evenly divisible by 4)
    for i in range(15):
        TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Configure: 15 teams, 4 teams per group
    data = {"teams_per_group": 4, "qualifying_per_group": 2, "matches_per_group": 3}

    response = client.post(f"/api/tournaments/{tournament.id}/rounds/1/configure/", data, format="json")

    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    # Should create 4 groups (3 with 4 teams, 1 with 3 teams)
    groups = Group.objects.filter(tournament=tournament, round_number=1)
    assert groups.count() == 4

    team_counts = [group.teams.count() for group in groups]
    assert 3 in team_counts  # At least one group with 3 teams
    assert sum(team_counts) == 15  # Total teams


@pytest.mark.django_db
def test_configure_round_18_teams_uneven_division_5_5_4_4(host_authenticated_client):
    """Test configuring round with 18 teams results in 5,5,4,4 distribution

    Logic: 18 teams, 4 teams per group
    - 18 / 4 = 4 groups with 2 remainder
    - Remainder 2 distributed as +1 to first 2 groups
    - Result: 5, 5, 4, 4
    """
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing", event_mode="TOURNAMENT")

    # Create exactly 18 registrations
    for i in range(18):
        TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Configure: 18 teams, 4 teams per group
    data = {"teams_per_group": 4, "qualifying_per_group": 2, "matches_per_group": 3}

    response = client.post(f"/api/tournaments/{tournament.id}/rounds/1/configure/", data, format="json")

    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    # Should create 4 groups
    groups = Group.objects.filter(tournament=tournament, round_number=1).order_by("group_name")
    assert groups.count() == 4

    # Get team counts for each group
    team_counts = [group.teams.count() for group in groups]
    team_counts.sort(reverse=True)  # Sort to get [5, 5, 4, 4]

    # Verify distribution is 5, 5, 4, 4
    assert team_counts == [5, 5, 4, 4], f"Expected [5, 5, 4, 4] but got {team_counts}"
    assert sum(team_counts) == 18  # Total teams


@pytest.mark.django_db
def test_configure_round_creates_matches(host_authenticated_client):
    """Test that configuring round creates correct number of matches"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing")

    for i in range(8):
        TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    data = {"teams_per_group": 4, "qualifying_per_group": 2, "matches_per_group": 5}

    response = client.post(f"/api/tournaments/{tournament.id}/rounds/1/configure/", data, format="json")

    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    # 2 groups, 5 matches each = 10 total matches
    assert Match.objects.filter(group__tournament=tournament).count() == 10


# ============================================================================
# MATCH SCORE UPDATE TESTS (SKIPPED - Match API endpoints not fully implemented)
# ============================================================================


@pytest.mark.django_db
def test_submit_match_scores(host_authenticated_client):
    """Test submitting scores for a match"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing")

    # Create group and match
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A", qualifying_teams=2)

    match = Match.objects.create(group=group, match_number=1, status="completed")

    # Create teams (TournamentRegistration objects)
    registrations = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(4)]
    for reg in registrations:
        group.teams.add(reg)

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Submit scores - Note: API expects 'wins', 'position_points', 'kill_points'
    scores_data = {
        "scores": [
            {"team_id": registrations[0].id, "kill_points": 15, "position_points": 10, "wins": 1},
            {"team_id": registrations[1].id, "kill_points": 10, "position_points": 6, "wins": 0},
            {"team_id": registrations[2].id, "kill_points": 8, "position_points": 4, "wins": 0},
            {"team_id": registrations[3].id, "kill_points": 5, "position_points": 2, "wins": 0},
        ]
    }

    response = client.post(f"/api/tournaments/{tournament.id}/matches/{match.id}/scores/", scores_data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert MatchScore.objects.filter(match=match).count() == 4

    # Check points calculation
    score1 = MatchScore.objects.get(match=match, team=registrations[0])
    assert score1.kill_points == 15
    assert score1.position_points == 10
    assert score1.wins == 1


@pytest.mark.django_db
def test_update_match_room_details(host_authenticated_client):
    """Test host can update match room ID and password using StartMatchView"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing")
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A")
    match = Match.objects.create(group=group, match_number=1, status="waiting")

    client = APIClient()
    client.force_authenticate(user=host.user)

    data = {"match_number": 1, "match_id": "ABC123", "match_password": "pass456"}

    # Use the correct endpoint: POST .../groups/<group_id>/matches/start/
    response = client.post(f"/api/tournaments/{tournament.id}/groups/{group.id}/matches/start/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    match.refresh_from_db()
    assert match.match_id == "ABC123"
    assert match.match_password == "pass456"
    assert match.status == "ongoing"


@pytest.mark.django_db
def test_player_can_see_room_details_when_registered(api_client):
    """Test registered player can see room details in group list"""
    host = HostProfileFactory()
    player_user = UserFactory(user_type="player")
    PlayerProfileFactory(user=player_user)

    tournament = TournamentFactory(host=host, status="ongoing")
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A")
    Match.objects.create(group=group, match_number=1, status="ongoing", match_id="ROOM123", match_password="secret")

    # Register player
    registration = TournamentRegistrationFactory(
        tournament=tournament, player=player_user.player_profile, status="confirmed"
    )
    group.teams.add(registration)

    client = APIClient()
    client.force_authenticate(user=player_user)

    # Use the correct endpoint: GET .../rounds/<round_number>/groups/
    response = client.get(f"/api/tournaments/{tournament.id}/rounds/1/groups/")

    assert response.status_code == status.HTTP_200_OK
    groups_data = response.data["groups"]
    match_data = groups_data[0]["matches"][0]
    assert match_data["match_id"] == "ROOM123"
    assert match_data["match_password"] == "secret"


@pytest.mark.django_db
def test_unregistered_player_cannot_see_room_details(api_client):
    """Test unregistered player cannot see room details (returns 403 or 404)"""
    host = HostProfileFactory()
    player_user = UserFactory(user_type="player")
    PlayerProfileFactory(user=player_user)

    tournament = TournamentFactory(host=host, status="ongoing")
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A")
    Match.objects.create(group=group, match_number=1, status="waiting", match_id="ROOM123", match_password="secret")

    client = APIClient()
    client.force_authenticate(user=player_user)

    # Try to access groups list for a tournament they aren't in
    response = client.get(f"/api/tournaments/{tournament.id}/rounds/1/groups/")

    # View returns 403 or 404 for non-registered players
    assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


# ============================================================================
# POINTS TABLE UPDATE TESTS
# ============================================================================


@pytest.mark.django_db
def test_round_scores_aggregate_from_matches(host_authenticated_client):
    """Test that round scores aggregate correctly from match scores"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing")
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A")

    team = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    group.teams.add(team)

    # Create 3 matches with scores
    for i in range(3):
        match = Match.objects.create(group=group, match_number=i + 1, status="completed")
        MatchScore.objects.create(match=match, team=team, kill_points=10, position_points=5)

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Trigger round score calculation
    from tournaments.services import TournamentGroupService

    TournamentGroupService.calculate_round_scores(tournament, 1)

    # Check round score
    round_score = RoundScore.objects.get(tournament=tournament, team=team, round_number=1)
    assert round_score.kill_points == 30  # 10 * 3
    assert round_score.position_points == 15  # 5 * 3
    assert round_score.total_points == 45


# ============================================================================
# QUALIFYING TEAMS LOGIC TESTS
# ============================================================================


@pytest.mark.django_db
def test_select_qualifying_teams_from_group(host_authenticated_client):
    """Test selecting top qualifying teams from group based on points"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing")
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Group A", qualifying_teams=2)

    # Create 4 teams with different scores
    teams = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(4)]
    for team in teams:
        group.teams.add(team)

    # Create round scores
    RoundScore.objects.create(tournament=tournament, team=teams[0], round_number=1, total_points=100)
    RoundScore.objects.create(tournament=tournament, team=teams[1], round_number=1, total_points=80)
    RoundScore.objects.create(tournament=tournament, team=teams[2], round_number=1, total_points=60)
    RoundScore.objects.create(tournament=tournament, team=teams[3], round_number=1, total_points=40)

    # Get top 2 qualifying teams
    qualifying = RoundScore.objects.filter(tournament=tournament, round_number=1).order_by("-total_points")[:2]

    assert qualifying.count() == 2
    assert qualifying[0].team == teams[0]
    assert qualifying[1].team == teams[1]


# ============================================================================
# NEXT ROUND ADVANCING TESTS
# ============================================================================


@pytest.mark.django_db
def test_advance_to_next_round_with_selected_teams(host_authenticated_client):
    """Test advancing to next round with selected qualifying teams"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[
            {"round": 1, "max_teams": 16, "qualifying_teams": 8},
            {"round": 2, "max_teams": 8, "qualifying_teams": 4},
        ],
    )

    # Create 16 teams
    teams = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(16)]

    # Select 8 teams for round 1
    tournament.selected_teams = {"1": [teams[i].id for i in range(8)]}
    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    # End round 1
    response = client.post(f"/api/tournaments/{tournament.id}/end-round/")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()

    # Should advance to round 2
    assert tournament.current_round == 2
    assert tournament.round_status["1"] == "completed"
    assert tournament.round_status["2"] == "ongoing"


@pytest.mark.django_db
def test_configure_round_2_with_round_1_qualifiers(host_authenticated_client):
    """Test configuring round 2 uses only round 1 qualifiers"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 16, "qualifying_teams": 8}, {"round": 2, "max_teams": 8}],
    )

    # Create 16 teams
    teams = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(16)]

    # Set round 1 qualifiers (8 teams)
    tournament.selected_teams = {"1": [teams[i].id for i in range(8)]}
    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Configure round 2
    data = {"teams_per_group": 4, "qualifying_per_group": 2, "matches_per_group": 3}

    response = client.post(f"/api/tournaments/{tournament.id}/rounds/2/configure/", data, format="json")

    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    # Should create 2 groups with 4 teams each (only the 8 qualifiers)
    groups = Group.objects.filter(tournament=tournament, round_number=2)
    assert groups.count() == 2

    total_teams = sum(group.teams.count() for group in groups)
    assert total_teams == 8


# ============================================================================
# ROUND RESULTS AND WINNER SELECTION TESTS
# ============================================================================


@pytest.mark.django_db
def test_get_round_results(api_client, host_user):
    """Test getting round results with rankings"""
    tournament = TournamentFactory(host=host_user.host_profile, status="ongoing")

    # Create group
    group = Group.objects.create(
        tournament=tournament, round_number=1, group_name="Group A", qualifying_teams=2, status="completed"
    )

    # Create match
    match = Match.objects.create(group=group, match_number=1, status="completed")

    # Create teams
    registrations = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(4)]
    for reg in registrations:
        group.teams.add(reg)

    # Create match scores (standings are calculated from MatchScore)
    MatchScore.objects.create(match=match, team=registrations[0], kill_points=60, position_points=40, wins=1)
    MatchScore.objects.create(match=match, team=registrations[1], kill_points=50, position_points=30, wins=0)
    MatchScore.objects.create(match=match, team=registrations[2], kill_points=40, position_points=20, wins=0)
    MatchScore.objects.create(match=match, team=registrations[3], kill_points=30, position_points=10, wins=0)

    # Use the correct endpoint: GET .../rounds/<round_number>/results/
    response = api_client.get(f"/api/tournaments/{tournament.id}/rounds/1/results/")

    assert response.status_code == status.HTTP_200_OK
    groups_data = response.data["groups"]
    standings = groups_data[0]["standings"]

    # Check rankings (standings should be sorted by total_points)
    assert standings[0]["team_id"] == registrations[0].id
    assert standings[0]["total_points"] == 100
    assert standings[1]["team_id"] == registrations[1].id
    assert standings[1]["total_points"] == 80


@pytest.mark.django_db
def test_select_tournament_winner(host_authenticated_client):
    """Test selecting tournament winner in final round"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],  # Final round
    )

    teams = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(2)]

    tournament.current_round = 2
    tournament.round_status = {"1": "completed", "2": "ongoing"}
    tournament.selected_teams = {"1": [teams[0].id, teams[1].id]}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Select winner
    data = {"winner_id": teams[0].id}
    response = client.post(f"/api/tournaments/{tournament.id}/select-winner/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    tournament.refresh_from_db()
    assert tournament.winners["2"] == teams[0].id


@pytest.mark.django_db
def test_cannot_select_winner_in_non_final_round(host_authenticated_client):
    """Test cannot select winner in non-final round"""
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="ongoing",
        rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}, {"round": 2, "max_teams": 2}],
    )

    team = TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    tournament.current_round = 1
    tournament.round_status = {"1": "ongoing"}
    tournament.save()

    client = APIClient()
    client.force_authenticate(user=host.user)

    data = {"winner_id": team.id}
    response = client.post(f"/api/tournaments/{tournament.id}/select-winner/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "final round" in response.data["error"].lower()
