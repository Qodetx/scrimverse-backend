import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import HostProfileFactory, TournamentFactory, TournamentRegistrationFactory
from tournaments.models import Group, Tournament


@pytest.fixture
def host_client():
    host_profile = HostProfileFactory()
    client = APIClient()
    client.force_authenticate(user=host_profile.user)
    return client, host_profile


@pytest.mark.django_db
def test_create_5v5_groups_with_bye(host_client):
    """Creating 5v5 groups with an odd number of teams assigns a bye team."""
    client, host_profile = host_client

    # Create a 5v5 tournament with 1 round
    tournament = TournamentFactory(
        host=host_profile,
        game_name="COD",
        rounds=[{"round": 1, "max_teams": 100, "qualifying_teams": 0}],
        status="upcoming",
    )

    # Create 3 confirmed registrations (odd number)
    regs = [TournamentRegistrationFactory(tournament=tournament, status="confirmed") for _ in range(3)]

    # Configure round: for 5v5 only matches_per_group is required
    data = {"matches_per_group": 3}
    response = client.post(f"/api/tournaments/{tournament.id}/rounds/1/configure/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    # Response should include bye_team and bye_message for odd teams
    assert "bye_team" in response.data
    assert response.data["bye_team"] is not None
    assert "bye_message" in response.data and response.data["bye_message"]

    # Check DB: groups created should be floor(3/2) = 1
    groups_count = Group.objects.filter(tournament=tournament, round_number=1).count()
    assert groups_count == 1

    # Tournament round_status should store bye_team_id in a dict
    tournament.refresh_from_db()
    assert tournament.round_status.get("1") is not None
    assert isinstance(tournament.round_status.get("1"), dict)
    # bye_team_id should be present in metadata when odd teams
    assert isinstance(tournament.round_status["1"].get("bye_team_id"), int)
