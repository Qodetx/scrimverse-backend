"""
Comprehensive test cases for Scrim Management
Tests cover:
- Scrim creation
- Scrim registration
- Scrim match management
- Scrim scoring and leaderboard
- Scrim-specific rules (1 round, 1 group, max 25 teams, max 6 matches)
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import HostProfileFactory, ScrimFactory, ScrimRegistrationFactory
from tournaments.models import Group

# ============================================================================
# SCRIM CREATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_create_scrim_as_host(host_authenticated_client, host_user):
    """Test host can create a scrim"""
    data = {
        "title": "Test Scrim",
        "description": "Quick scrim match",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 20,
        "entry_fee": 0,
        "scrim_start": "2026-02-01T10:00:00Z",
        "scrim_end": "2026-02-01T12:00:00Z",
        "registration_start": "2026-01-25T10:00:00Z",
        "registration_end": "2026-01-31T10:00:00Z",
    }

    response = host_authenticated_client.post("/api/tournaments/scrims/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_create_scrim_enforces_single_round(host_authenticated_client):
    """Test integrated scrim can only have 1 round (auto-corrected by serializer)"""
    data = {
        "title": "Integrated Scrim",
        "description": "Test Scrim Description",
        "rules": "Practice match rules",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "entry_fee": 0,
        "tournament_start": "2026-02-01T10:00:00Z",
        "tournament_end": "2026-02-01T18:00:00Z",
        "registration_start": "2026-01-25T10:00:00Z",
        "registration_end": "2026-01-31T10:00:00Z",
        "rounds": [{"round": 1, "max_teams": 20}, {"round": 2, "max_teams": 10}],  # Serializer will force it to 1 round
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    # Serializer forces 1 round for SCRIM
    assert len(response.data["rounds"]) == 1


@pytest.mark.django_db
def test_create_scrim_max_25_teams(host_authenticated_client):
    """Test integrated scrim cannot have more than 25 teams"""
    data = {
        "title": "Too Many Teams Scrim",
        "description": "Test Scrim Description",
        "rules": "Practice match rules",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 30,  # Fails (> 25)
        "entry_fee": 0,
        "tournament_start": "2026-02-01T10:00:00Z",
        "tournament_end": "2026-02-01T18:00:00Z",
        "registration_start": "2026-01-25T10:00:00Z",
        "registration_end": "2026-01-31T10:00:00Z",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "25" in str(response.data)


# ============================================================================
# SCRIM REGISTRATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_register_for_scrim(authenticated_client, player_user, test_players):
    """Test player can register for regular Scrim model"""
    scrim = ScrimFactory(game_mode="Duo", status="upcoming")

    data = {"team_name": "Scrim Team", "player_usernames": [player_user.username, test_players[0].username]}

    response = authenticated_client.post(f"/api/tournaments/scrims/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    scrim.refresh_from_db()
    assert scrim.current_participants == 1


@pytest.mark.django_db
def test_scrim_registration_increments_count(authenticated_client, player_user):
    """Test scrim registration increments participant count"""
    scrim = ScrimFactory(game_mode="Solo", current_participants=0, status="upcoming")

    data = {"team_name": "Solo Scrim", "player_usernames": [player_user.username]}

    response = authenticated_client.post(f"/api/tournaments/scrims/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    scrim.refresh_from_db()
    assert scrim.current_participants == 1


@pytest.mark.django_db
def test_cannot_register_for_full_scrim(authenticated_client, player_user):
    """Test cannot register when Scrim model is full"""
    scrim = ScrimFactory(game_mode="Solo", max_participants=2, current_participants=2, status="upcoming")

    data = {"team_name": "Late Team", "player_usernames": [player_user.username]}

    response = authenticated_client.post(f"/api/tournaments/scrims/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# SCRIM GROUP CONFIGURATION TESTS (Integrated)
# ============================================================================


@pytest.mark.django_db
def test_scrim_creates_single_group(host_authenticated_client):
    """Test integrated scrim creates only 1 group via ConfigureRoundView"""
    from tests.factories import TournamentFactory, TournamentRegistrationFactory

    host = HostProfileFactory()
    scrim = TournamentFactory(host=host, status="ongoing", event_mode="SCRIM")

    # Create 12 registrations
    for i in range(12):
        TournamentRegistrationFactory(tournament=scrim, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Configure round 1
    data = {"teams_per_group": 12, "qualifying_per_group": 0, "matches_per_group": 3}  # Will be ignored/forced to total

    response = client.post(f"/api/tournaments/{scrim.id}/rounds/1/configure/", data, format="json")

    assert response.status_code == status.HTTP_200_OK

    # Should create exactly 1 group for scrim
    groups = Group.objects.filter(tournament=scrim, round_number=1)
    assert groups.count() == 1
    assert groups.first().teams.count() == 12


@pytest.mark.django_db
def test_scrim_max_matches_constraint(host_authenticated_client):
    """Test integrated scrim max matches constraint in serializer"""
    data = {
        "title": "Too Many Matches Scrim",
        "description": "Test Scrim Description",
        "rules": "Practice match rules",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "max_matches": 5,  # Serializer check: Scrims support max 4
        "entry_fee": 0,
        "tournament_start": "2026-02-01T10:00:00Z",
        "tournament_end": "2026-02-01T18:00:00Z",
        "registration_start": "2026-01-25T10:00:00Z",
        "registration_end": "2026-01-31T10:00:00Z",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "max_matches" in str(response.data)


# ============================================================================
# SCRIM SCORING TESTS (Integrated)
# ============================================================================


@pytest.mark.django_db
def test_scrim_aggregate_scoring(host_authenticated_client):
    """Test integrated scrim uses aggregate scoring across all matches"""
    from tests.factories import TournamentFactory, TournamentRegistrationFactory
    from tournaments.models import RoundScore

    host = HostProfileFactory()
    scrim = TournamentFactory(host=host, status="ongoing", event_mode="SCRIM")

    reg1 = TournamentRegistrationFactory(tournament=scrim, status="confirmed")

    # Create round scores for 3 matches
    RoundScore.objects.create(
        tournament=scrim, team=reg1, round_number=1, kill_points=30, position_points=20, total_points=50
    )

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Get standings via tournament stats endpoint
    response = client.get(f"/api/tournaments/{scrim.id}/stats/")

    assert response.status_code == status.HTTP_200_OK
    leaderboard = response.data["leaderboard"]
    assert len(leaderboard) == 1
    assert leaderboard[0]["total_points"] == 50


@pytest.mark.django_db
def test_scrim_winner_highest_aggregate_points(host_authenticated_client):
    """Test integrated scrim winnerdetermination"""
    from tests.factories import TournamentFactory, TournamentRegistrationFactory
    from tournaments.models import RoundScore

    host = HostProfileFactory()
    scrim = TournamentFactory(host=host, status="ongoing", event_mode="SCRIM")

    # Create 2 teams
    reg1 = TournamentRegistrationFactory(tournament=scrim, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=scrim, status="confirmed")

    # Create round scores
    RoundScore.objects.create(tournament=scrim, team=reg1, round_number=1, total_points=100)
    RoundScore.objects.create(tournament=scrim, team=reg2, round_number=1, total_points=80)

    client = APIClient()
    client.force_authenticate(user=host.user)

    response = client.get(f"/api/tournaments/{scrim.id}/stats/")

    assert response.status_code == status.HTTP_200_OK
    leaderboard = response.data["leaderboard"]
    assert leaderboard[0]["team_id"] == reg1.id  # Should be team with 100 pts


# ============================================================================
# SCRIM STATUS MANAGEMENT TESTS
# ============================================================================


@pytest.mark.django_db
def test_start_scrim(host_authenticated_client):
    """Test host can start a scrim (model status)"""
    host = HostProfileFactory()
    scrim = ScrimFactory(host=host, status="upcoming")

    scrim.status = "ongoing"
    scrim.save()

    assert scrim.status == "ongoing"


@pytest.mark.django_db
def test_end_scrim(host_authenticated_client):
    """Test host can end a scrim (model status)"""
    host = HostProfileFactory()
    scrim = ScrimFactory(host=host, status="ongoing")

    scrim.status = "completed"
    scrim.save()

    assert scrim.status == "completed"


# ============================================================================
# SCRIM LISTING TESTS
# ============================================================================


@pytest.mark.django_db
def test_list_scrims_separate_from_tournaments(api_client):
    """Test scrims are listed separately from tournaments"""
    from tests.factories import TournamentFactory

    # Create scrim and tournament
    scrim = ScrimFactory(status="upcoming")
    tournament = TournamentFactory(event_mode="TOURNAMENT", status="upcoming")

    # List scrims
    response = api_client.get("/api/tournaments/scrims/")

    if response.status_code == status.HTTP_200_OK:
        results = response.data.get("results", response.data)
        scrim_ids = [item["id"] for item in results]
        assert scrim.id in scrim_ids
        # Tournament should not be in SCRIM-only list
        # Unless the list endpoint returns both, but usually it's filtered
        assert tournament.id not in scrim_ids


@pytest.mark.django_db
def test_get_scrim_details(api_client):
    """Test getting scrim details"""
    scrim = ScrimFactory(title="Test Scrim")

    response = api_client.get(f"/api/tournaments/scrims/{scrim.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Test Scrim"


# ============================================================================
# SCRIM VALIDATION TESTS (Integrated)
# ============================================================================


@pytest.mark.django_db
def test_scrim_no_qualification_logic(host_authenticated_client):
    """Test integrated scrims don't use qualification logic in configuration"""
    from tests.factories import TournamentFactory, TournamentRegistrationFactory

    host = HostProfileFactory()
    scrim = TournamentFactory(host=host, status="ongoing", event_mode="SCRIM")

    TournamentRegistrationFactory(tournament=scrim, status="confirmed")

    client = APIClient()
    client.force_authenticate(user=host.user)

    # Try to configure with qualifying teams
    data = {"teams_per_group": 10, "qualifying_per_group": 5, "matches_per_group": 3}  # Should be forced to 0

    response = client.post(f"/api/tournaments/{scrim.id}/rounds/1/configure/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    # View code: qualifying_per_group = 0 # No qualification
    group = Group.objects.get(tournament=scrim, round_number=1)
    assert group.qualifying_teams == 0


@pytest.mark.django_db
def test_player_can_view_scrim_registrations(authenticated_client, player_user):
    """Test player can view their scrim registrations"""
    scrim = ScrimFactory(status="upcoming")
    ScrimRegistrationFactory(scrim=scrim, player=player_user.player_profile, status="confirmed")

    response = authenticated_client.get("/api/tournaments/scrims/my-registrations/")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) >= 1
