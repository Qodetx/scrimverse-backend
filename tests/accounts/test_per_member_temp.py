"""
Integration tests for the per-member temporary team behavior.

Covers:
  - team_helpers.has_permanent_team_for_game
  - team_helpers.determine_member_temp_status
  - team_helpers.is_team_temporary_for_user
  - perform_create flow (captain without perm team -> perm team created)
  - perm-team-per-game block when captain already has a perm team for that game
  - invite acceptance flow (member without perm team -> perm membership)
  - invite acceptance flow (member with perm team -> temp membership)
  - convert_permanent (per-member)
  - decline_conversion (per-member, non-captain leaves)
  - decline_conversion (captain blocked)
  - cleanup_expired_temp_teams (membership-only expiry)
  - cleanup_expired_temp_teams (orphan team deleted when last member leaves)
  - serializer is_temporary_for_me
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from accounts.models import Team, TeamJoinRequest, TeamMember, User
from accounts.team_helpers import (
    determine_member_temp_status,
    has_permanent_team_for_game,
    is_team_temporary_for_user,
)
from tests.factories import PlayerProfileFactory, UserFactory


# ────────────────────────── helpers ──────────────────────────


def _make_perm_team(captain, game="BGMI", name="Existing Perm Team"):
    """Create a permanent team and add captain as a perm member."""
    team = Team.objects.create(
        name=name, captain=captain, is_temporary=False, game=game,
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    return team


# ────────────────────────── helper unit tests ──────────────────────────


@pytest.mark.django_db
def test_has_permanent_team_for_game_true_when_perm_membership_exists():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    _make_perm_team(user, game="BGMI")
    assert has_permanent_team_for_game(user, "BGMI") is True


@pytest.mark.django_db
def test_has_permanent_team_for_game_false_for_different_game():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    _make_perm_team(user, game="BGMI")
    assert has_permanent_team_for_game(user, "Valorant") is False


@pytest.mark.django_db
def test_has_permanent_team_for_game_false_when_only_temp_membership():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    team = Team.objects.create(name="Temp", captain=user, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=user, username=user.username,
        is_captain=True, is_temporary=True,
    )
    assert has_permanent_team_for_game(user, "BGMI") is False


@pytest.mark.django_db
def test_determine_member_temp_status_perm_when_no_existing():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    is_temp, deadline = determine_member_temp_status(user, "BGMI")
    assert is_temp is False
    assert deadline is None


@pytest.mark.django_db
def test_determine_member_temp_status_temp_when_existing_perm():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    _make_perm_team(user, game="BGMI")
    is_temp, deadline = determine_member_temp_status(user, "BGMI")
    assert is_temp is True
    assert deadline is not None
    # Deadline must be ~48h in the future
    assert (deadline - timezone.now()) > timedelta(hours=47)


@pytest.mark.django_db
def test_is_team_temporary_for_user_legacy_team_temp_for_everyone():
    user = UserFactory(user_type="player")
    PlayerProfileFactory(user=user)
    team = Team.objects.create(name="Legacy", captain=user, is_temporary=True)
    TeamMember.objects.create(
        team=team, user=user, username=user.username, is_captain=True, is_temporary=False,
    )
    # Even though TeamMember.is_temporary is False, legacy team flag wins
    assert is_team_temporary_for_user(team, user) is True


@pytest.mark.django_db
def test_is_team_temporary_for_user_per_member_only_for_specific_user():
    captain = UserFactory(user_type="player")
    PlayerProfileFactory(user=captain)
    other = UserFactory(user_type="player", username="other")
    PlayerProfileFactory(user=other)

    team = Team.objects.create(name="Mixed", captain=captain, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    TeamMember.objects.create(
        team=team, user=other, username=other.username,
        is_captain=False, is_temporary=True,
        conversion_deadline=timezone.now() + timedelta(hours=48),
    )

    # Captain sees it as perm
    assert is_team_temporary_for_user(team, captain) is False
    # Other user sees it as temp
    assert is_team_temporary_for_user(team, other) is True


# ────────────────────────── serializer tests ──────────────────────────


@pytest.mark.django_db
def test_serializer_is_temporary_for_me_perm_member(authenticated_client, player_user):
    """Captain who is not temp should see is_temporary_for_me=False."""
    team = _make_perm_team(player_user, game="BGMI", name="My Team")
    response = authenticated_client.get(f"/api/accounts/teams/{team.id}/")
    assert response.status_code == 200
    assert response.data["is_temporary_for_me"] is False
    assert response.data["my_conversion_deadline"] is None


@pytest.mark.django_db
def test_serializer_is_temporary_for_me_temp_member(authenticated_client, player_user):
    """Member with TeamMember.is_temporary=True should see is_temporary_for_me=True."""
    team = Team.objects.create(name="Temp For Me", captain=player_user, is_temporary=False, game="BGMI")
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=True, is_temporary=True, conversion_deadline=deadline,
    )
    response = authenticated_client.get(f"/api/accounts/teams/{team.id}/")
    assert response.status_code == 200
    assert response.data["is_temporary_for_me"] is True
    assert response.data["my_conversion_deadline"] is not None


# ────────────────────────── perform_create flow ──────────────────────────


@pytest.mark.django_db
def test_create_team_no_existing_perm_creates_perm(authenticated_client, player_user):
    """Player with no perm team for BGMI can create a BGMI team — captain's membership is perm."""
    data = {"name": "Fresh Squad", "game": "BGMI", "player_usernames": []}
    response = authenticated_client.post("/api/accounts/teams/", data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    team = Team.objects.get(name="Fresh Squad")
    captain_member = TeamMember.objects.get(team=team, user=player_user)
    assert captain_member.is_captain is True
    assert captain_member.is_temporary is False


@pytest.mark.django_db
def test_create_team_with_existing_perm_for_same_game_blocked(authenticated_client, player_user):
    """Cannot create a second perm team for the same game."""
    _make_perm_team(player_user, game="BGMI")
    data = {"name": "Second BGMI Team", "game": "BGMI"}
    response = authenticated_client.post("/api/accounts/teams/", data, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_team_with_existing_perm_for_different_game_allowed(authenticated_client, player_user):
    """Player can have a perm team per game."""
    _make_perm_team(player_user, game="BGMI")
    data = {"name": "Valorant Team", "game": "Valorant"}
    response = authenticated_client.post("/api/accounts/teams/", data, format="json")
    assert response.status_code == status.HTTP_201_CREATED


# ────────────────────────── invite acceptance flow ──────────────────────────


@pytest.mark.django_db
def test_invite_accept_perm_member_when_no_existing_perm(authenticated_client, player_user):
    """User without perm team accepting an invite gets a perm membership."""
    inviter = UserFactory(user_type="player", username="inv_perm")
    PlayerProfileFactory(user=inviter)
    team = _make_perm_team(inviter, game="BGMI", name="Inviter Team")

    invite = TeamJoinRequest.objects.create(
        team=team, player=player_user, request_type="invite", status="pending",
    )
    response = authenticated_client.post(
        "/api/accounts/teams/handle_invite/",
        {"invite_id": invite.id, "action": "accept"}, format="json",
    )
    assert response.status_code == 200, response.data
    member = TeamMember.objects.get(team=team, user=player_user)
    assert member.is_temporary is False


@pytest.mark.django_db
def test_invite_accept_temp_member_when_existing_perm(authenticated_client, player_user):
    """User who already has a perm team for the game gets a TEMP membership on accept."""
    # player_user already has a perm BGMI team
    _make_perm_team(player_user, game="BGMI", name="My Existing Team")

    inviter = UserFactory(user_type="player", username="inv_temp")
    PlayerProfileFactory(user=inviter)
    other_team = Team.objects.create(name="Other BGMI Team", captain=inviter, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=other_team, user=inviter, username=inviter.username,
        is_captain=True, is_temporary=False,
    )

    invite = TeamJoinRequest.objects.create(
        team=other_team, player=player_user, request_type="invite", status="pending",
    )
    response = authenticated_client.post(
        "/api/accounts/teams/handle_invite/",
        {"invite_id": invite.id, "action": "accept"}, format="json",
    )
    assert response.status_code == 200
    member = TeamMember.objects.get(team=other_team, user=player_user)
    assert member.is_temporary is True
    assert member.conversion_deadline is not None


# ────────────────────────── convert / decline endpoints ──────────────────────────


@pytest.mark.django_db
def test_convert_permanent_per_member_marks_membership_perm(authenticated_client, player_user):
    """convert_permanent on a per-member temp marks just that user's TeamMember.is_temporary=False."""
    captain = UserFactory(user_type="player", username="capt")
    PlayerProfileFactory(user=captain)
    team = Team.objects.create(name="Mixed Team", captain=captain, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username, is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    membership = TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )
    # player_user has no other perm team -> conversion succeeds
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/convert_permanent/")
    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.is_temporary is False
    assert membership.conversion_deadline is None


@pytest.mark.django_db
def test_convert_permanent_per_member_blocked_when_existing_perm(authenticated_client, player_user):
    """convert_permanent returns 409 when user already has a perm team for the game."""
    # player_user already has a perm BGMI team
    _make_perm_team(player_user, game="BGMI", name="My Existing Team")

    captain = UserFactory(user_type="player", username="capt2")
    PlayerProfileFactory(user=captain)
    team = Team.objects.create(name="New BGMI Team", captain=captain, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username, is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )

    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/convert_permanent/")
    assert response.status_code == 409
    assert response.data.get("error") == "conflict"


@pytest.mark.django_db
def test_decline_conversion_per_member_removes_member(authenticated_client, player_user):
    """decline_conversion on a non-captain temp member removes them from the team."""
    captain = UserFactory(user_type="player", username="cap3")
    PlayerProfileFactory(user=captain)
    team = Team.objects.create(name="Decline Team", captain=captain, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username, is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )

    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/decline_conversion/")
    assert response.status_code == 200
    assert TeamMember.objects.filter(team=team, user=player_user).exists() is False
    # Team and captain still exist
    assert Team.objects.filter(id=team.id).exists()


@pytest.mark.django_db
def test_decline_conversion_per_member_captain_blocked(authenticated_client, player_user):
    """Captain cannot decline their own membership (would orphan the team)."""
    team = Team.objects.create(name="Captain Decline", captain=player_user, is_temporary=False, game="BGMI")
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=True, is_temporary=True, conversion_deadline=deadline,
    )
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/decline_conversion/")
    assert response.status_code == 400


# ────────────────────────── cleanup task ──────────────────────────


@pytest.mark.django_db
def test_cleanup_expired_per_member_removes_membership():
    """Cleanup task removes only expired memberships, not the entire team."""
    from tournaments.tasks.tournament_tasks import cleanup_expired_temp_teams

    captain = UserFactory(user_type="player", username="cap_cl")
    PlayerProfileFactory(user=captain)
    member = UserFactory(user_type="player", username="member_cl")
    PlayerProfileFactory(user=member)

    team = Team.objects.create(name="Cleanup Team", captain=captain, is_temporary=False, game="BGMI")
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username, is_captain=True, is_temporary=False,
    )
    expired_membership = TeamMember.objects.create(
        team=team, user=member, username=member.username,
        is_captain=False, is_temporary=True,
        conversion_deadline=timezone.now() - timedelta(hours=1),  # expired
    )

    cleanup_expired_temp_teams()

    assert TeamMember.objects.filter(id=expired_membership.id).exists() is False
    assert Team.objects.filter(id=team.id).exists()
    assert TeamMember.objects.filter(team=team, user=captain).exists()


@pytest.mark.django_db
def test_cleanup_does_not_remove_captain_membership():
    """Cleanup never auto-removes captain membership (would orphan team)."""
    from tournaments.tasks.tournament_tasks import cleanup_expired_temp_teams

    captain = UserFactory(user_type="player", username="cap_capt")
    PlayerProfileFactory(user=captain)

    team = Team.objects.create(name="Captain Only", captain=captain, is_temporary=False, game="BGMI")
    captain_member = TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=True,
        conversion_deadline=timezone.now() - timedelta(hours=1),  # expired
    )

    cleanup_expired_temp_teams()

    assert TeamMember.objects.filter(id=captain_member.id).exists() is True


@pytest.mark.django_db
def test_cleanup_legacy_team_temp_still_works():
    """Legacy team-level temp cleanup path still deletes whole team."""
    from tournaments.tasks.tournament_tasks import cleanup_expired_temp_teams

    captain = UserFactory(user_type="player", username="cap_legacy")
    PlayerProfileFactory(user=captain)

    team = Team.objects.create(
        name="Legacy Temp",
        captain=captain,
        is_temporary=True,
        conversion_deadline=timezone.now() - timedelta(hours=1),
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username, is_captain=True, is_temporary=False,
    )

    cleanup_expired_temp_teams()

    assert Team.objects.filter(id=team.id).exists() is False
