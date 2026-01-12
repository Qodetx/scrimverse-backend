"""
Tests for team lifecycle management
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import TeamJoinRequest, TeamMember
from tests.factories import TeamFactory, UserFactory


@pytest.mark.django_db
def test_transfer_captaincy():
    """Test transferring team captaincy to another member"""
    captain = UserFactory(user_type="player", username="captain")
    new_captain_user = UserFactory(user_type="player", username="new_captain")
    team = TeamFactory(captain=captain)

    # Add captain as member
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    # Add candidate for new captain
    candidate = TeamMember.objects.create(
        team=team, user=new_captain_user, username=new_captain_user.username, is_captain=False
    )

    client = APIClient()
    client.force_authenticate(user=captain)

    response = client.post(f"/api/accounts/teams/{team.id}/transfer_captaincy/", {"member_id": candidate.id})

    assert response.status_code == status.HTTP_200_OK
    team.refresh_from_db()
    assert team.captain == new_captain_user

    candidate.refresh_from_db()
    assert candidate.is_captain is True


@pytest.mark.django_db
def test_leave_team():
    """Test a non-captain member leaving a team"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)

    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    member = TeamMember.objects.create(team=team, user=player, username=player.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=player)

    response = client.post(f"/api/accounts/teams/{team.id}/leave_team/")

    assert response.status_code == status.HTTP_200_OK
    assert not TeamMember.objects.filter(id=member.id).exists()


@pytest.mark.django_db
def test_captain_cannot_leave_team():
    """Test that captain cannot leave the team without transferring captaincy"""
    captain = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    client = APIClient()
    client.force_authenticate(user=captain)

    response = client.post(f"/api/accounts/teams/{team.id}/leave_team/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Captains cannot leave" in response.data["error"]


@pytest.mark.django_db
def test_remove_member():
    """Test captain removing a member from the team"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)

    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    member = TeamMember.objects.create(team=team, user=player, username=player.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=captain)

    response = client.post(f"/api/accounts/teams/{team.id}/remove_member/", {"member_id": member.id})

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not TeamMember.objects.filter(id=member.id).exists()


@pytest.mark.django_db
def test_non_captain_cannot_remove_member():
    """Test that non-captain cannot remove members"""
    captain = UserFactory(user_type="player")
    player1 = UserFactory(user_type="player")
    player2 = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)

    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    TeamMember.objects.create(team=team, user=player1, username=player1.username, is_captain=False)
    member2 = TeamMember.objects.create(team=team, user=player2, username=player2.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=player1)

    response = client.post(f"/api/accounts/teams/{team.id}/remove_member/", {"member_id": member2.id})

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert TeamMember.objects.filter(id=member2.id).exists()


@pytest.mark.django_db
def test_request_join_team():
    """Test a player requesting to join a team"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    client = APIClient()
    client.force_authenticate(user=player)

    response = client.post(f"/api/accounts/teams/{team.id}/request_join/")

    assert response.status_code == status.HTTP_201_CREATED
    assert TeamJoinRequest.objects.filter(team=team, player=player, request_type="request").exists()


@pytest.mark.django_db
def test_invite_player_to_team():
    """Test captain inviting a player to the team"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    client = APIClient()
    client.force_authenticate(user=captain)

    response = client.post(f"/api/accounts/teams/{team.id}/invite_player/", {"player_id": player.id})

    assert response.status_code == status.HTTP_201_CREATED
    assert TeamJoinRequest.objects.filter(team=team, player=player, request_type="invite").exists()


@pytest.mark.django_db
def test_handle_invitation_accept():
    """Test a player accepting a team invitation (via handle_invite action)"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)
    invite = TeamJoinRequest.objects.create(team=team, player=player, request_type="invite", status="pending")

    client = APIClient()
    client.force_authenticate(user=player)

    # Field name is invite_id, not invitation_id
    response = client.post("/api/accounts/teams/handle_invite/", {"invite_id": invite.id, "action": "accept"})

    assert response.status_code == status.HTTP_200_OK
    assert TeamMember.objects.filter(team=team, user=player).exists()
    assert not TeamJoinRequest.objects.filter(id=invite.id, status="pending").exists()


@pytest.mark.django_db
def test_appoint_new_captain():
    """Test captain appointing a new captain"""
    captain = UserFactory(user_type="player")
    player = UserFactory(user_type="player")
    team = TeamFactory(captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    member = TeamMember.objects.create(team=team, user=player, username=player.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=captain)

    response = client.post(f"/api/accounts/teams/{team.id}/appoint_captain/", {"member_id": member.id})

    assert response.status_code == status.HTTP_200_OK
    team.refresh_from_db()
    assert team.captain == player
    member.refresh_from_db()
    assert member.is_captain is True
