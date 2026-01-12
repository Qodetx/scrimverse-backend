"""
Comprehensive test cases for Team Management
Tests cover:
- Team creation
- Captain management
- Member invitation and removal
- Join requests (accept/decline)
- Team permissions
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Team, TeamJoinRequest, TeamMember
from tests.factories import PlayerProfileFactory, UserFactory

# ============================================================================
# TEAM CREATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_create_team_as_player(authenticated_client, player_user):
    """Test player can create a team"""
    data = {
        "name": "Alpha Squad",
        "description": "Best team ever",
        "player_usernames": [],
    }

    response = authenticated_client.post("/api/accounts/teams/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert Team.objects.filter(name="Alpha Squad").exists()
    team = Team.objects.get(name="Alpha Squad")
    assert team.captain == player_user
    assert TeamMember.objects.filter(team=team, user=player_user, is_captain=True).exists()


@pytest.mark.django_db
def test_create_team_with_members(authenticated_client, player_user, test_players):
    """Test creating team with initial members"""
    data = {
        "name": "Beta Squad",
        "description": "Team with members",
        "player_usernames": [test_players[0].username, test_players[1].username],
    }

    response = authenticated_client.post("/api/accounts/teams/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    team = Team.objects.get(name="Beta Squad")
    assert team.members.count() == 3  # Captain + 2 members
    assert TeamMember.objects.filter(team=team, username=test_players[0].username).exists()


@pytest.mark.django_db
def test_create_team_when_already_in_team_fails(authenticated_client, player_user):
    """Test player cannot create team if already in a permanent team"""
    # Create first team
    team1 = Team.objects.create(name="First Team", captain=player_user, is_temporary=False)
    TeamMember.objects.create(team=team1, user=player_user, username=player_user.username, is_captain=True)

    # Try to create second team
    data = {"name": "Second Team", "description": "Should fail"}
    response = authenticated_client.post("/api/accounts/teams/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already a member" in str(response.data).lower()


@pytest.mark.django_db
def test_host_cannot_create_team(host_authenticated_client):
    """Test host cannot create a team"""
    data = {"name": "Host Team", "description": "Should fail"}
    response = host_authenticated_client.post("/api/accounts/teams/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# CAPTAIN MANAGEMENT TESTS
# ============================================================================


@pytest.mark.django_db
def test_transfer_captaincy(authenticated_client, player_user, test_players):
    """Test captain can transfer captaincy to another member"""
    # Create team with members
    team = Team.objects.create(name="Transfer Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)
    member = TeamMember.objects.create(
        team=team, user=test_players[0], username=test_players[0].username, is_captain=False
    )

    # Transfer captaincy
    data = {"member_id": member.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/transfer_captaincy/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    team.refresh_from_db()
    assert team.captain == test_players[0]
    member.refresh_from_db()
    assert member.is_captain is True


@pytest.mark.django_db
def test_non_captain_cannot_transfer_captaincy(api_client, test_players):
    """Test non-captain cannot transfer captaincy"""
    captain = test_players[0]
    member = test_players[1]

    team = Team.objects.create(name="Test Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    member_obj = TeamMember.objects.create(team=team, user=member, username=member.username, is_captain=False)

    # Try to transfer as non-captain
    client = APIClient()
    client.force_authenticate(user=member)

    data = {"member_id": member_obj.id}
    response = client.post(f"/api/accounts/teams/{team.id}/transfer_captaincy/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# MEMBER INVITATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_captain_invite_player(authenticated_client, player_user, test_players):
    """Test captain can invite a player"""
    team = Team.objects.create(name="Invite Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    data = {"player_id": test_players[0].id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/invite_player/", data, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert TeamJoinRequest.objects.filter(
        team=team, player=test_players[0], request_type="invite", status="pending"
    ).exists()


@pytest.mark.django_db
def test_non_captain_cannot_invite(api_client, test_players):
    """Test non-captain cannot invite players"""
    captain = test_players[0]
    member = test_players[1]
    invitee = test_players[2]

    team = Team.objects.create(name="Test Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    TeamMember.objects.create(team=team, user=member, username=member.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=member)

    data = {"player_id": invitee.id}
    response = client.post(f"/api/accounts/teams/{team.id}/invite_player/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_invite_player_already_in_team_fails(authenticated_client, player_user, test_players):
    """Test cannot invite player who is already in a team"""
    team = Team.objects.create(name="Team 1", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    # Put test_players[0] in another team
    other_team = Team.objects.create(name="Team 2", captain=test_players[1], is_temporary=False)
    TeamMember.objects.create(team=other_team, user=test_players[0], username=test_players[0].username)

    data = {"player_id": test_players[0].id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/invite_player/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already a member" in str(response.data).lower()


@pytest.mark.django_db
def test_invite_when_team_full_fails(authenticated_client, player_user):
    """Test cannot invite when team is full (15 members)"""
    team = Team.objects.create(name="Full Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    # Add 14 more members (total 15)
    for i in range(14):
        user = UserFactory(user_type="player", username=f"member{i}")
        PlayerProfileFactory(user=user)
        TeamMember.objects.create(team=team, user=user, username=user.username)

    # Try to invite 16th member
    new_player = UserFactory(user_type="player")
    PlayerProfileFactory(user=new_player)

    data = {"player_id": new_player.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/invite_player/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "full" in str(response.data).lower()


# ============================================================================
# ACCEPT/DECLINE INVITATION TESTS
# ============================================================================


@pytest.mark.django_db
def test_player_accept_invitation(api_client, test_players):
    """Test player can accept team invitation"""
    captain = test_players[0]
    player = test_players[1]

    team = Team.objects.create(name="Accept Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    # Create invitation
    invite = TeamJoinRequest.objects.create(team=team, player=player, request_type="invite", status="pending")

    # Accept invitation
    client = APIClient()
    client.force_authenticate(user=player)

    data = {"invite_id": invite.id, "action": "accept"}
    response = client.post("/api/accounts/teams/handle_invite/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert TeamMember.objects.filter(team=team, user=player).exists()
    invite.refresh_from_db()
    assert invite.status == "accepted"


@pytest.mark.django_db
def test_player_reject_invitation(api_client, test_players):
    """Test player can reject team invitation"""
    captain = test_players[0]
    player = test_players[1]

    team = Team.objects.create(name="Reject Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    invite = TeamJoinRequest.objects.create(team=team, player=player, request_type="invite", status="pending")

    client = APIClient()
    client.force_authenticate(user=player)

    data = {"invite_id": invite.id, "action": "reject"}
    response = client.post("/api/accounts/teams/handle_invite/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert not TeamMember.objects.filter(team=team, user=player).exists()
    invite.refresh_from_db()
    assert invite.status == "rejected"


# ============================================================================
# JOIN REQUEST TESTS
# ============================================================================


@pytest.mark.django_db
def test_player_request_to_join_team(api_client, test_players):
    """Test player can request to join a team"""
    captain = test_players[0]
    player = test_players[1]

    team = Team.objects.create(name="Join Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)

    client = APIClient()
    client.force_authenticate(user=player)

    response = client.post(f"/api/accounts/teams/{team.id}/request_join/")

    assert response.status_code == status.HTTP_201_CREATED
    assert TeamJoinRequest.objects.filter(team=team, player=player, request_type="request", status="pending").exists()


@pytest.mark.django_db
def test_captain_accept_join_request(authenticated_client, player_user, test_players):
    """Test captain can accept join request"""
    team = Team.objects.create(name="Accept Request Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    # Create join request
    join_request = TeamJoinRequest.objects.create(
        team=team, player=test_players[0], request_type="request", status="pending"
    )

    data = {"request_id": join_request.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/accept_request/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert TeamMember.objects.filter(team=team, user=test_players[0]).exists()
    join_request.refresh_from_db()
    assert join_request.status == "accepted"


@pytest.mark.django_db
def test_captain_reject_join_request(authenticated_client, player_user, test_players):
    """Test captain can reject join request"""
    team = Team.objects.create(name="Reject Request Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    join_request = TeamJoinRequest.objects.create(
        team=team, player=test_players[0], request_type="request", status="pending"
    )

    data = {"request_id": join_request.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/reject_request/", data, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert not TeamMember.objects.filter(team=team, user=test_players[0]).exists()
    join_request.refresh_from_db()
    assert join_request.status == "rejected"


# ============================================================================
# REMOVE MEMBER TESTS
# ============================================================================


@pytest.mark.django_db
def test_captain_remove_member(authenticated_client, player_user, test_players):
    """Test captain can remove a member"""
    team = Team.objects.create(name="Remove Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)
    member = TeamMember.objects.create(team=team, user=test_players[0], username=test_players[0].username)

    data = {"member_id": member.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/remove_member/", data, format="json")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not TeamMember.objects.filter(id=member.id).exists()


@pytest.mark.django_db
def test_captain_cannot_remove_self(authenticated_client, player_user):
    """Test captain cannot remove themselves"""
    team = Team.objects.create(name="Self Remove Team", captain=player_user)
    captain_member = TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username, is_captain=True
    )

    data = {"member_id": captain_member.id}
    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/remove_member/", data, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "captain" in str(response.data).lower()


@pytest.mark.django_db
def test_non_captain_cannot_remove_member(api_client, test_players):
    """Test non-captain cannot remove members"""
    captain = test_players[0]
    member1 = test_players[1]
    member2 = test_players[2]

    team = Team.objects.create(name="Test Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    TeamMember.objects.create(team=team, user=member1, username=member1.username, is_captain=False)
    member2_obj = TeamMember.objects.create(team=team, user=member2, username=member2.username, is_captain=False)

    # Try to remove as non-captain
    client = APIClient()
    client.force_authenticate(user=member1)

    data = {"member_id": member2_obj.id}
    response = client.post(f"/api/accounts/teams/{team.id}/remove_member/", data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# LEAVE TEAM TESTS
# ============================================================================


@pytest.mark.django_db
def test_member_leave_team(api_client, test_players):
    """Test member can leave a team"""
    captain = test_players[0]
    member = test_players[1]

    team = Team.objects.create(name="Leave Team", captain=captain)
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    member_obj = TeamMember.objects.create(team=team, user=member, username=member.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=member)

    response = client.post(f"/api/accounts/teams/{team.id}/leave_team/")

    assert response.status_code == status.HTTP_200_OK
    assert not TeamMember.objects.filter(id=member_obj.id).exists()


@pytest.mark.django_db
def test_captain_cannot_leave_team(authenticated_client, player_user):
    """Test captain cannot leave team (must transfer captaincy first)"""
    team = Team.objects.create(name="Captain Leave Team", captain=player_user)
    TeamMember.objects.create(team=team, user=player_user, username=player_user.username, is_captain=True)

    response = authenticated_client.post(f"/api/accounts/teams/{team.id}/leave_team/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "captain" in str(response.data).lower()


# ============================================================================
# GET TEAM DETAILS TESTS
# ============================================================================


@pytest.mark.django_db
def test_get_team_details(api_client, test_players):
    """Test getting team details"""
    captain = test_players[0]
    team = Team.objects.create(name="Details Team", captain=captain, description="Test description")
    TeamMember.objects.create(team=team, user=captain, username=captain.username, is_captain=True)
    TeamMember.objects.create(team=team, user=test_players[1], username=test_players[1].username)

    response = api_client.get(f"/api/accounts/teams/{team.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == "Details Team"
    assert response.data["description"] == "Test description"
    assert len(response.data["members"]) == 2


@pytest.mark.django_db
def test_get_my_teams(api_client, test_players):
    """Test getting user's teams"""
    player = test_players[0]

    team1 = Team.objects.create(name="My Team 1", captain=player)
    TeamMember.objects.create(team=team1, user=player, username=player.username, is_captain=True)

    team2 = Team.objects.create(name="My Team 2", captain=test_players[1])
    TeamMember.objects.create(team=team2, user=test_players[1], username=test_players[1].username, is_captain=True)
    TeamMember.objects.create(team=team2, user=player, username=player.username, is_captain=False)

    client = APIClient()
    client.force_authenticate(user=player)

    response = client.get("/api/accounts/teams/?mine=true")

    assert response.status_code == status.HTTP_200_OK
    results = response.data.get("results", response.data)
    assert len(results) == 2
