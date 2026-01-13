"""
Test cases for Scrim functionality using Tournament model with event_mode='SCRIM'
Tests cover:
- Scrim creation with proper constraints
- Scrim registration
- Scrim-specific validations (max 25 teams, 1 round, max 4 matches)
- Scrim filtering
"""
import pytest
from rest_framework import status

from tests.factories import TournamentFactory
from tournaments.models import Tournament, TournamentRegistration

# ============================================================================
# SCRIM CREATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_create_scrim_as_host(host_authenticated_client, host_user):
    """Test host can create a scrim using Tournament model with event_mode='SCRIM'"""
    data = {
        "title": "Practice Scrim",
        "description": "Quick practice match",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "entry_fee": "100.00",
        "prize_pool": "2000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Standard scrim rules",
        "max_matches": 4,
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["event_mode"] == "SCRIM"
    assert response.data["title"] == "Practice Scrim"

    # Verify scrim was created in database
    scrim = Tournament.objects.get(id=response.data["id"])
    assert scrim.event_mode == "SCRIM"
    assert len(scrim.rounds) == 1  # Scrims should have 1 round
    assert scrim.rounds[0]["qualifying_teams"] == 0  # No qualification in scrims


@pytest.mark.django_db
def test_create_scrim_enforces_max_25_teams(host_authenticated_client):
    """Test scrim cannot have more than 25 teams"""
    data = {
        "title": "Large Scrim",
        "description": "Too many teams",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 30,  # Exceeds limit
        "entry_fee": "100.00",
        "prize_pool": "5000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Standard rules",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "25" in str(response.data)


@pytest.mark.django_db
def test_create_scrim_enforces_single_round(host_authenticated_client):
    """Test scrim automatically gets 1 round regardless of input"""
    data = {
        "title": "Multi-Round Scrim",
        "description": "Should be forced to 1 round",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "entry_fee": "100.00",
        "prize_pool": "2000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Standard rules",
        "rounds": [
            {"round": 1, "max_teams": 20},
            {"round": 2, "max_teams": 10},  # This should be ignored
        ],
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    scrim = Tournament.objects.get(id=response.data["id"])
    assert len(scrim.rounds) == 1  # Should be forced to 1 round
    assert scrim.rounds[0]["round"] == 1


@pytest.mark.django_db
def test_create_scrim_max_matches_constraint(host_authenticated_client):
    """Test scrim cannot have more than 4 matches"""
    data = {
        "title": "Too Many Matches Scrim",
        "description": "Exceeds match limit",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "entry_fee": "100.00",
        "prize_pool": "2000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Standard rules",
        "max_matches": 6,  # Exceeds limit of 4
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "4" in str(response.data)


# ============================================================================
# SCRIM REGISTRATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_register_for_scrim(authenticated_client, player_user, test_players, host_user):
    """Test player can register for scrim"""
    scrim = TournamentFactory(
        host=host_user.host_profile,
        event_mode="SCRIM",
        game_mode="Squad",
        status="upcoming",
        max_participants=25,
    )

    data = {
        "team_name": "Scrim Squad",
        "player_usernames": [
            player_user.username,
            test_players[0].username,
            test_players[1].username,
            test_players[2].username,
        ],
    }

    response = authenticated_client.post(f"/api/tournaments/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert TournamentRegistration.objects.filter(tournament=scrim).exists()

    scrim.refresh_from_db()
    assert scrim.current_participants == 1


@pytest.mark.django_db
def test_scrim_registration_increments_count(authenticated_client, player_user, test_players, host_user):
    """Test scrim registration increments participant count"""
    scrim = TournamentFactory(
        host=host_user.host_profile,
        event_mode="SCRIM",
        game_mode="Duo",
        status="upcoming",
        max_participants=25,
        current_participants=0,
    )

    data = {
        "team_name": "Duo Team",
        "player_usernames": [player_user.username, test_players[0].username],
    }

    response = authenticated_client.post(f"/api/tournaments/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    scrim.refresh_from_db()
    assert scrim.current_participants == 1


@pytest.mark.django_db
def test_cannot_register_for_full_scrim(authenticated_client, player_user, host_user):
    """Test cannot register when scrim is full"""
    scrim = TournamentFactory(
        host=host_user.host_profile,
        event_mode="SCRIM",
        game_mode="Solo",
        status="upcoming",
        max_participants=2,
        current_participants=2,  # Already full
    )

    data = {"team_name": "Late Team", "player_usernames": [player_user.username]}

    response = authenticated_client.post(f"/api/tournaments/{scrim.id}/register/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "full" in str(response.data).lower()


# ============================================================================
# SCRIM FILTERING TESTS
# ============================================================================


@pytest.mark.django_db
def test_filter_scrims_by_event_mode(api_client, host_user):
    """Test filtering tournaments to get only scrims"""
    # Create mix of tournaments and scrims
    TournamentFactory(host=host_user.host_profile, event_mode="TOURNAMENT", title="Tournament 1")
    TournamentFactory(host=host_user.host_profile, event_mode="SCRIM", title="Scrim 1")
    TournamentFactory(host=host_user.host_profile, event_mode="TOURNAMENT", title="Tournament 2")
    TournamentFactory(host=host_user.host_profile, event_mode="SCRIM", title="Scrim 2")

    response = api_client.get("/api/tournaments/?event_mode=SCRIM")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) == 2
    assert all(item["event_mode"] == "SCRIM" for item in results)


@pytest.mark.django_db
def test_filter_tournaments_excludes_scrims(api_client, host_user):
    """Test filtering for tournaments excludes scrims"""
    TournamentFactory(host=host_user.host_profile, event_mode="TOURNAMENT", title="Tournament 1")
    TournamentFactory(host=host_user.host_profile, event_mode="SCRIM", title="Scrim 1")
    TournamentFactory(host=host_user.host_profile, event_mode="TOURNAMENT", title="Tournament 2")

    response = api_client.get("/api/tournaments/?event_mode=TOURNAMENT")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) == 2
    assert all(item["event_mode"] == "TOURNAMENT" for item in results)


# ============================================================================
# SCRIM LIFECYCLE TESTS
# ============================================================================


@pytest.mark.django_db
def test_scrim_status_transitions(host_user):
    """Test scrim can transition through statuses"""
    scrim = TournamentFactory(
        host=host_user.host_profile,
        event_mode="SCRIM",
        status="upcoming",
    )

    assert scrim.status == "upcoming"

    scrim.status = "ongoing"
    scrim.save()
    scrim.refresh_from_db()
    assert scrim.status == "ongoing"

    scrim.status = "completed"
    scrim.save()
    scrim.refresh_from_db()
    assert scrim.status == "completed"


@pytest.mark.django_db
def test_scrim_has_basic_plan_type(host_authenticated_client):
    """Test scrims automatically get basic plan type"""
    data = {
        "title": "Free Scrim",
        "description": "Practice match",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 20,
        "entry_fee": "0.00",
        "prize_pool": "0.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Standard rules",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    scrim = Tournament.objects.get(id=response.data["id"])
    assert scrim.plan_type == "basic"


# ============================================================================
# SCRIM GAME MODE TESTS
# ============================================================================


@pytest.mark.django_db
def test_create_solo_scrim(host_authenticated_client):
    """Test creating solo mode scrim"""
    data = {
        "title": "Solo Scrim",
        "description": "Solo practice",
        "game_name": "BGMI",
        "game_mode": "Solo",
        "event_mode": "SCRIM",
        "max_participants": 25,
        "entry_fee": "50.00",
        "prize_pool": "1000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T11:00:00Z",
        "rules": "Solo rules",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["game_mode"] == "Solo"
    assert response.data["event_mode"] == "SCRIM"


@pytest.mark.django_db
def test_create_duo_scrim(host_authenticated_client):
    """Test creating duo mode scrim"""
    data = {
        "title": "Duo Scrim",
        "description": "Duo practice",
        "game_name": "BGMI",
        "game_mode": "Duo",
        "event_mode": "SCRIM",
        "max_participants": 25,
        "entry_fee": "100.00",
        "prize_pool": "2000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T11:00:00Z",
        "rules": "Duo rules",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["game_mode"] == "Duo"
    assert response.data["event_mode"] == "SCRIM"


@pytest.mark.django_db
def test_create_squad_scrim(host_authenticated_client):
    """Test creating squad mode scrim"""
    data = {
        "title": "Squad Scrim",
        "description": "Squad practice",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "event_mode": "SCRIM",
        "max_participants": 25,
        "entry_fee": "200.00",
        "prize_pool": "5000.00",
        "registration_start": "2026-01-20T08:00:00Z",
        "registration_end": "2026-01-20T09:00:00Z",
        "tournament_start": "2026-01-20T10:00:00Z",
        "tournament_end": "2026-01-20T12:00:00Z",
        "rules": "Squad rules",
    }

    response = host_authenticated_client.post("/api/tournaments/create/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["game_mode"] == "Squad"
    assert response.data["event_mode"] == "SCRIM"
