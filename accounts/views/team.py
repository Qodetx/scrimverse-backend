import logging
import uuid

from django.db import models
from django.utils import timezone

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, User
from accounts.notification_utils import should_notify
from accounts.serializers import (
    TeamInviteDetailSerializer,
    TeamJoinRequestSerializer,
    TeamMemberSerializer,
    TeamSerializer,
)
from accounts.tasks import process_team_invitation
from tournaments.models import RoundScore, TournamentRegistration

logger = logging.getLogger(__name__)


class IsPlayerUser(permissions.BasePermission):
    """
    Permission class to allow access only to player users
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "player"


class TeamViewSet(viewsets.ModelViewSet):
    """
    Team Management API
    """

    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """
        Allow unauthenticated access for list and retrieve actions
        """
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsPlayerUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        # For list action, check for "mine" parameter to filter by user's teams
        if self.action == "list":
            mine = self.request.query_params.get("mine") == "true"
            search = self.request.query_params.get("search", "").strip()

            if mine:
                queryset = Team.objects.filter(
                    models.Q(captain=self.request.user) | models.Q(members__user=self.request.user)
                ).distinct().order_by('-created_at')
            else:
                queryset = Team.objects.filter(is_temporary=False)  # hide temp teams from public browse

            # Apply search filter if provided
            if search:
                queryset = queryset.filter(name__icontains=search)

            # Apply game filter if provided
            game = self.request.query_params.get("game", "").strip()
            if game and game.upper() != "ALL":
                queryset = queryset.filter(game__iexact=game)

            return queryset

        # For actions that handle their own permission checks or should return 403 instead of 404
        # we return all teams and let the action/update/delete method handle the check.
        if self.action in [
            "retrieve",
            "update",
            "partial_update",
            "destroy",
            "leave_team",
            "request_join",
            "past_tournaments",
            "transfer_captaincy",
            "invite_player",
            "remove_member",
            "add_member",
            "accept_request",
            "reject_request",
            "appoint_captain",
            "join_requests",
            "send_invites",
            "generate_invite_link",
            "set_member_role",
        ]:
            return Team.objects.all()

        # Fallback
        return Team.objects.all()

    @action(detail=True, methods=["post"])
    def leave_team(self, request, pk=None):
        """Allow a player to leave a team"""
        team = self.get_object()

        # Check if user is a member
        member = TeamMember.objects.filter(team=team, user=request.user).first()
        if not member:
            return Response({"error": "You are not a member of this team"}, status=status.HTTP_400_BAD_REQUEST)

        # Block leaving a confirmed tournament temp team after registration closes
        if team.is_temporary and team.linked_tournament:
            linked_t = team.linked_tournament
            if linked_t.registration_end and timezone.now() > linked_t.registration_end:
                return Response(
                    {"error": "Registration has closed. You cannot leave this tournament team."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if captain
        if team.captain == request.user:
            # Captain is leaving - check if there are other members
            other_members = TeamMember.objects.filter(team=team).exclude(user=request.user).order_by("id")

            if other_members.exists():
                # Promote the oldest member (first added) to captain
                new_captain_member = other_members.first()

                if new_captain_member.user:
                    # Update team captain
                    team.captain = new_captain_member.user
                    team.save()

                    # Update captain flags
                    TeamMember.objects.filter(team=team).update(is_captain=False)
                    new_captain_member.is_captain = True
                    new_captain_member.save()

                    # Remove the old captain
                    member.delete()

                    logger.info(
                        f"Captain {request.user.username} left team {team.name}. "
                        f"New captain: {new_captain_member.username}"
                    )

                    return Response(
                        {
                            "message": f"You have left the team. {new_captain_member.username} is now the captain.",
                            "new_captain": new_captain_member.username,
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    # Next member is not a registered user, cannot promote
                    return Response(
                        {
                            "error": "Cannot leave: next member is not a registered user. Please remove them first or delete the team."  # noqa: E501
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                # Captain is the only member - delete the team
                team_name = team.name
                team.delete()

                logger.info(f"Team {team_name} deleted as captain {request.user.username} was the only member")

                return Response(
                    {
                        "message": f"Team '{team_name}' has been deleted as you were the only member.",
                        "team_deleted": True,
                    },
                    status=status.HTTP_200_OK,
                )

        # Regular member leaving
        member.delete()
        logger.info(f"Member {request.user.username} left team {team.name}")
        return Response({"message": "Successfully left the team"}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        logger.debug(
            f"Create team request - Captain: {self.request.user.id}, Team name: {self.request.data.get('name')}"
        )

        # Check if user is already in a PERMANENT team for the same game (temporary teams are allowed)
        game = self.request.data.get('game', '')
        existing_membership = TeamMember.objects.filter(
            user=self.request.user, team__is_temporary=False, team__game=game
        ).exists()
        if existing_membership:
            raise ValidationError({"error": f"You already have a permanent {game} team. Leave it first before creating a new one."})

        player_usernames = self.request.data.get("player_usernames", [])

        # ✅ VALIDATE: All player_usernames must be registered players
        if player_usernames:
            invalid_usernames = []
            for username in player_usernames:
                if username and username != self.request.user.username:
                    user_exists = User.objects.filter(username=username, user_type="player").exists()
                    if not user_exists:
                        invalid_usernames.append(username)

            if invalid_usernames:
                raise ValidationError(
                    {
                        "error": f"The following players were not found: {', '.join(invalid_usernames)}. Only registered ScrimVerse players can be added to teams."  # noqa: E501
                    }
                )

        team = serializer.save(captain=self.request.user)
        logger.debug(f"Team created - ID: {team.id}, Name: {team.name}, Captain: {self.request.user.username}")

        # Add captain as the first member
        TeamMember.objects.create(
            team=team, user=self.request.user, username=self.request.user.username, is_captain=True
        )

        # Add additional members from player_usernames (all validated now)
        for username in player_usernames:
            if username and username != self.request.user.username:
                user_obj = User.objects.get(username=username, user_type="player")  # Use .get() since we validated
                TeamMember.objects.create(team=team, username=username, user=user_obj, is_captain=False)

    def update(self, request, *args, **kwargs):
        """Update team details (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can edit team details"}, status=status.HTTP_403_FORBIDDEN)

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(team, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """Partial update team details (captain only)"""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        team = self.get_object()

        logger.debug(
            f"Add member request - Team: {team.id}, Captain: {request.user.id}, New member: {request.data.get('username')}"  # noqa E501
        )

        if team.captain != request.user:
            return Response({"error": "Only the captain can add members"}, status=status.HTTP_403_FORBIDDEN)

        if team.members.count() >= 15:
            return Response({"error": "Team cannot have more than 15 members"}, status=status.HTTP_400_BAD_REQUEST)

        username = request.data.get("username")
        if not username:
            return Response({"error": "Username is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ VALIDATE: User must exist and be a player
        user = User.objects.filter(username=username, user_type="player").first()
        if not user:
            return Response(
                {"error": f"Player '{username}' not found. Only registered ScrimVerse players can be added to teams."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already a member
        if TeamMember.objects.filter(team=team, username=username).exists():
            return Response({"error": "Member already exists"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user is already in another PERMANENT team for the same game
        if TeamMember.objects.filter(user=user, team__is_temporary=False, team__game=team.game).exclude(team=team).exists():
            return Response(
                {"error": f"{username} is already a member of another {team.game} team"}, status=status.HTTP_400_BAD_REQUEST
            )

        member = TeamMember.objects.create(team=team, username=username, user=user, is_captain=False)

        logger.debug(f"Member added - Team: {team.id}, Member: {username}, User ID: {user.id}")

        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can remove members"}, status=status.HTTP_403_FORBIDDEN)

        # Block removal after tournament registration closes
        if team.is_temporary and team.linked_tournament:
            linked_t = team.linked_tournament
            if linked_t.registration_end and timezone.now() > linked_t.registration_end:
                return Response(
                    {"error": "Registration has closed. Team roster is locked."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        member_id = request.data.get("member_id")
        member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not member:
            return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        if member.user == team.captain:
            return Response(
                {"error": "Cannot remove the captain. Transfer captaincy first."}, status=status.HTTP_400_BAD_REQUEST
            )

        removed_user = member.user
        member.delete()

        # If temp team: remove from registration JSON and auto-promote next unregistered member
        if team.is_temporary:
            try:
                from tournaments.models import TournamentRegistration
                registration = TournamentRegistration.objects.filter(team=team, status='confirmed').first()
                if registration and removed_user:
                    player_profile = getattr(removed_user, 'player_profile', None)
                    removed_player_id = player_profile.id if player_profile else None

                    # Remove from team_members JSON
                    if registration.team_members:
                        registration.team_members = [
                            m for m in registration.team_members
                            if m.get('player_id') != removed_player_id
                            and m.get('username', '').lower() != removed_user.username.lower()
                        ]

                    # Remove from invited_members_status
                    if registration.invited_members_status:
                        for key in list(registration.invited_members_status.keys()):
                            if registration.invited_members_status[key].get('username', '').lower() == removed_user.username.lower():
                                del registration.invited_members_status[key]
                                break

                    # Determine cap for this game mode
                    mode_map = {'5v5': 5, 'Squad': 4, 'Duo': 2, 'Solo': 1}
                    game_mode = registration.tournament.game_mode if registration.tournament else None
                    mode_cap = mode_map.get(game_mode, 15)

                    # Auto-promote next team member not yet registered
                    current_registered = len(registration.team_members or []) + 1  # +1 for captain
                    if current_registered < mode_cap:
                        registered_usernames = {m.get('username', '').lower() for m in (registration.team_members or [])}
                        captain_username = team.captain.username.lower() if team.captain else ''
                        registered_usernames.add(captain_username)

                        next_member = TeamMember.objects.filter(team=team).exclude(
                            user__username__in=registered_usernames
                        ).exclude(user=team.captain).first()

                        if next_member:
                            next_user = next_member.user
                            next_profile = getattr(next_user, 'player_profile', None)
                            next_player_id = next_profile.id if next_profile else None
                            if registration.team_members is None:
                                registration.team_members = []
                            registration.team_members.append({
                                'username': next_user.username,
                                'player_id': next_player_id,
                                'is_registered': True,
                            })
                            if registration.invited_members_status is None:
                                registration.invited_members_status = {}
                            registration.invited_members_status[next_user.username] = {
                                'status': 'accepted',
                                'username': next_user.username,
                            }

                    registration.save(update_fields=['team_members', 'invited_members_status', 'updated_at'])
            except Exception as e:
                logger.error(f"Failed to update registration after member removal: {e}")

        # Notify the removed player
        if removed_user:
            try:
                from accounts.models import Notification
                Notification.objects.create(
                    user=removed_user,
                    type="general",
                    title="Removed from Team",
                    message=f"You have been removed from '{team.name}' by captain {request.user.username}.",
                )
            except Exception:
                pass

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transfer_captaincy(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response(
                {"error": "Only the current captain can transfer captaincy"}, status=status.HTTP_403_FORBIDDEN
            )
        if team.is_temporary and team.linked_tournament and team.linked_tournament.registration_end < timezone.now():
            return Response({"error": "Registration has closed. Captaincy transfer is locked."}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        new_captain_member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not new_captain_member or not new_captain_member.user:
            return Response(
                {"error": "New captain must be a registered user in the team"}, status=status.HTTP_400_BAD_REQUEST
            )

        old_captain = request.user
        new_captain_user = new_captain_member.user

        # Update team captain
        team.captain = new_captain_user
        team.save()

        # Update flags
        TeamMember.objects.filter(team=team).update(is_captain=False)
        new_captain_member.is_captain = True
        new_captain_member.save()

        # Send notifications
        try:
            from accounts.models import Notification

            # Notify the new captain
            Notification.objects.create(
                user=new_captain_user,
                type="general",
                title="You're the Captain Now!",
                message=f"You have been transferred captaincy of '{team.name}' by {old_captain.username}.",
            )

            # Notify all other members (excluding old and new captain)
            other_members = TeamMember.objects.filter(team=team).exclude(user__in=[old_captain, new_captain_user])
            for m in other_members:
                if m.user:
                    Notification.objects.create(
                        user=m.user,
                        type="general",
                        title="Captain Changed",
                        message=f"The captain of '{team.name}' has changed. The new captain is {new_captain_user.username}.",
                    )
        except Exception:
            pass

        return Response(TeamSerializer(team).data)

    @action(detail=True, methods=["post"])
    def request_join(self, request, pk=None):
        """Player requests to join a team"""
        team = self.get_object()

        logger.debug(f"Join request - Team: {team.id}, Player: {request.user.id}")

        # Only players can request to join a team
        if request.user.user_type != "player":
            return Response({"error": "Only players can request to join a team"}, status=status.HTTP_403_FORBIDDEN)

        # Check if the requester is the team captain
        if team.captain_id == request.user.id:
            return Response({"error": "You are the captain of this team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user is already a direct member of THIS team
        if TeamMember.objects.filter(user=request.user, team=team).exists():
            return Response({"error": "You are already a member of this team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user is already in a PERMANENT team for the same game
        if team.game and TeamMember.objects.filter(user=request.user, team__is_temporary=False, team__game=team.game).exists():
            return Response({"error": f"You are already a member of a {team.game} team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if team is full
        if team.members.count() >= 15:
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        # Check for existing pending request (separate from invite)
        existing_request = TeamJoinRequest.objects.filter(
            team=team, player=request.user, request_type="request"
        ).first()

        if existing_request:
            if existing_request.status == "pending":
                return Response({"error": "You already have a pending join request for this team"}, status=status.HTTP_400_BAD_REQUEST)
            elif existing_request.status == "accepted":
                # Stale accepted record — user was removed. Allow re-requesting.
                existing_request.status = "pending"
                existing_request.save()
                join_request = existing_request
            elif existing_request.status == "rejected":
                # Allow re-requesting after rejection
                existing_request.status = "pending"
                existing_request.save()
                join_request = existing_request
            else:
                join_request = existing_request
        else:
            join_request = TeamJoinRequest.objects.create(
                team=team, player=request.user, status="pending", request_type="request"
            )

        logger.debug(
            f"Join request created - Team: {team.id}, Player: {request.user.username}, Status: {join_request.status}"
        )

        # Notify the team captain about the join request
        try:
            from accounts.models import Notification
            if should_notify(team.captain, 'tournamentUpdates'):
                Notification.objects.create(
                    user=team.captain,
                    type="general",
                    title="New Join Request",
                    message=f"{request.user.username} has requested to join your team {team.name}.",
                    related_id=team.id,
                    related_type="team",
                )
        except Exception as notify_err:
            # Notification failure should not block the join request from being recorded
            logger.warning(f"Failed to send join request notification: {notify_err}")

        return Response({"message": "Join request sent"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def invite_player(self, request, pk=None):
        """Captain invites a player to the team"""
        team = self.get_object()

        logger.debug(
            f"Invite player request - Team: {team.id}, Captain: {request.user.id}, Player ID: {request.data.get('player_id')}"  # noqa E501
        )

        if team.captain != request.user:
            return Response({"error": "Only captains can invite players"}, status=status.HTTP_403_FORBIDDEN)
        if team.is_temporary and team.linked_tournament and team.linked_tournament.registration_end < timezone.now():
            return Response({"error": "Registration has closed. New invites are not allowed."}, status=status.HTTP_403_FORBIDDEN)

        player_id = request.data.get("player_id")
        if not player_id:
            return Response({"error": "player_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            player = User.objects.get(id=player_id, user_type="player")
        except User.DoesNotExist:
            return Response({"error": "Player not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if player is already in a PERMANENT team for the same game
        if TeamMember.objects.filter(user=player, team__is_temporary=False, team__game=team.game).exists():
            return Response({"error": f"Player is already a member of a {team.game} team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if team is full
        if team.members.count() >= 15:
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update invite
        invite, created = TeamJoinRequest.objects.get_or_create(
            team=team, player=player, defaults={"status": "pending", "request_type": "invite"}
        )

        if not created:
            if invite.status == "rejected":
                invite.status = "pending"
                invite.request_type = "invite"
                invite.save()
            elif invite.request_type == "request" and invite.status == "pending":
                # Automatically accept if player already requested to join
                TeamMember.objects.create(team=team, user=player, username=player.username, is_captain=False)
                invite.status = "accepted"
                invite.save()
                return Response(
                    {"message": "Player already had a join request. They have been added to the team."},
                    status=status.HTTP_200_OK,
                )

        # Process invitation async (email notifications disabled for now)
        process_team_invitation.delay(team.id, player.id, "invite")

        return Response({"message": "Invitation sent"}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def my_invites(self, request):
        """Get pending team-management invitations for the current user"""
        invites = TeamJoinRequest.objects.filter(player=request.user, status="pending", request_type="invite")
        serializer = TeamJoinRequestSerializer(invites, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_tournament_invites(self, request):
        """
        Get pending tournament registration invites matched by the logged-in user's email.
        """
        email = request.user.email
        invites = TeamJoinRequest.objects.filter(
            invited_email__iexact=email,
            status="pending",
            invite_token__isnull=False,
        ).select_related(
            "team",
            "tournament_registration__tournament",
            "tournament_registration__player__user",
        )
        data = []
        for inv in invites:
            reg = inv.tournament_registration
            tournament = reg.tournament if reg else None
            captain_name = reg.player.user.username if (reg and reg.player) else "Unknown"
            data.append({
                "invite_token": str(inv.invite_token),
                "team_name": inv.team.name if inv.team else "",
                "tournament_name": tournament.title if tournament else "",
                "captain_name": captain_name,
                "invite_expires_at": inv.invite_expires_at,
            })
        return Response(data)

    @action(detail=False, methods=["post"])
    def handle_invite(self, request):
        """Accept or reject an invitation"""
        invite_id = request.data.get("invite_id")
        action = request.data.get("action")  # 'accept' or 'reject'

        if not invite_id or action not in ["accept", "reject"]:
            return Response({"error": "invite_id and valid action are required"}, status=status.HTTP_400_BAD_REQUEST)

        invite = TeamJoinRequest.objects.filter(
            id=invite_id, player=request.user, status="pending", request_type="invite"
        ).first()
        if not invite:
            return Response({"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND)

        if action == "accept":
            team = invite.team
            # Check if player is already in a permanent team for the same game (only block for permanent teams)
            if not team.is_temporary and TeamMember.objects.filter(user=request.user, team__is_temporary=False, team__game=team.game).exists():
                return Response({"error": f"You are already a member of a {team.game} team"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if player is already registered in the same tournament via another team
            if invite.tournament_registration:
                tournament = invite.tournament_registration.tournament
                already_registered = TeamMember.objects.filter(
                    user=request.user,
                    team__tournament_registrations__tournament=tournament,
                    team__tournament_registrations__status='confirmed',
                ).exclude(team=team).exists()
                if already_registered:
                    return Response(
                        {"error": f"You are already registered for '{tournament.title}' with another team."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Check if team is full
            if team.members.count() >= 15:
                return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

            # Add member
            TeamMember.objects.create(team=team, user=request.user, username=request.user.username, is_captain=False)
            invite.status = "accepted"
            invite.save()

            # Update invited_members_status on the linked TournamentRegistration
            if invite.tournament_registration:
                registration = invite.tournament_registration
                if not registration.invited_members_status:
                    registration.invited_members_status = {}
                match_key = request.user.username  # username invite uses username as key
                for contact_key in list(registration.invited_members_status.keys()):
                    if contact_key.lower() == match_key.lower():
                        registration.invited_members_status[contact_key]['status'] = 'accepted'
                        registration.invited_members_status[contact_key]['username'] = request.user.username
                        break
                registration.save(update_fields=['invited_members_status', 'updated_at'])

            return Response({"message": "Invitation accepted"}, status=status.HTTP_200_OK)
        else:
            invite.status = "rejected"
            invite.save()

            # Notify the captain that the invite was rejected
            try:
                from accounts.models import Notification
                captain = invite.team.captain
                if captain:
                    Notification.objects.create(
                        user=captain,
                        type="general",
                        title="Invite Declined",
                        message=f"{request.user.username} has declined your invitation to join '{invite.team.name}'.",
                    )
            except Exception:
                pass

            return Response({"message": "Invitation rejected"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def join_requests(self, request, pk=None):
        """Get pending join requests for a team (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only captains can view join requests"}, status=status.HTTP_403_FORBIDDEN)

        requests = team.join_requests.filter(status="pending", request_type="request")
        serializer = TeamJoinRequestSerializer(requests, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def accept_request(self, request, pk=None):
        """Accept a join request (captain only)"""
        logger = logging.getLogger("accounts")
        team = self.get_object()

        logger.info(
            f"Accept request attempt - Team: {team.id} ({team.name}), Captain: {request.user.id} ({request.user.username})"  # noqa E501
        )

        if team.captain != request.user:
            logger.warning(f"Unauthorized accept attempt - User {request.user.id} is not captain of team {team.id}")
            return Response({"error": "Only captains can accept requests"}, status=status.HTTP_403_FORBIDDEN)

        request_id = request.data.get("request_id")
        logger.debug(f"Processing join request ID: {request_id} for team {team.id}")

        join_request = team.join_requests.filter(id=request_id, status="pending").first()

        if not join_request:
            logger.error(f"Join request {request_id} not found or not pending for team {team.id}")
            return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Found join request - Player: {join_request.player.id} ({join_request.player.username})")

        # Check if team is full
        current_member_count = team.members.count()
        if current_member_count >= 15:
            logger.warning(f"Team {team.id} is full ({current_member_count}/15 members)")
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Add member
            new_member = TeamMember.objects.create(
                team=team, user=join_request.player, username=join_request.player.username, is_captain=False
            )
            logger.info(
                f"Created team member - Member ID: {new_member.id}, User: {join_request.player.username}, Team: {team.name}"  # noqa E501
            )

            join_request.status = "accepted"
            join_request.save()
            logger.info(f"Join request {request_id} accepted successfully")

            try:
                from accounts.models import Notification
                Notification.objects.create(
                    user=join_request.player,
                    type="general",
                    title="Join Request Accepted",
                    message=f"Your request to join '{team.name}' has been accepted! Check the Team tab.",
                    related_id=team.id,
                    related_type="team",
                )
            except Exception:
                pass

            return Response({"message": "Request accepted"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error accepting join request {request_id}: {str(e)}", exc_info=True)
            return Response({"error": "Failed to accept request"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def reject_request(self, request, pk=None):
        """Reject a join request (captain only)"""
        logger = logging.getLogger("accounts")
        team = self.get_object()

        logger.info(
            f"Reject request attempt - Team: {team.id} ({team.name}), Captain: {request.user.id} ({request.user.username})"  # noqa E501
        )

        if team.captain != request.user:
            logger.warning(f"Unauthorized reject attempt - User {request.user.id} is not captain of team {team.id}")
            return Response({"error": "Only captains can reject requests"}, status=status.HTTP_403_FORBIDDEN)

        request_id = request.data.get("request_id")
        logger.debug(f"Processing rejection for join request ID: {request_id}")

        join_request = team.join_requests.filter(id=request_id, status="pending").first()

        if not join_request:
            logger.error(f"Join request {request_id} not found or not pending for team {team.id}")
            return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Rejecting join request from player: {join_request.player.id} ({join_request.player.username})")

        join_request.status = "rejected"
        join_request.save()

        logger.info(f"Join request {request_id} rejected successfully")

        try:
            from accounts.models import Notification
            Notification.objects.create(
                user=join_request.player,
                type="general",
                title="Join Request Declined",
                message=f"Your request to join '{team.name}' has been declined.",
                related_id=team.id,
                related_type="team",
            )
        except Exception:
            pass

        return Response({"message": "Request rejected"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def appoint_captain(self, request, pk=None):
        """Appoint a new captain (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only captains can appoint new captains"}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        member = team.members.filter(id=member_id).first()

        if not member or not member.user:
            return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        # Update team captain
        team.captain = member.user
        team.save()

        # Update member roles
        team.members.update(is_captain=False)
        member.is_captain = True
        member.save()

        return Response({"message": "Captain appointed"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def past_tournaments(self, request, pk=None):
        """Get past tournaments for a team"""
        team = self.get_object()

        # Get all completed tournaments this team participated in
        registrations = (
            TournamentRegistration.objects.filter(team=team, tournament__status="completed", status="confirmed")
            .select_related("tournament")
            .order_by("-tournament__tournament_end")
        )

        tournaments_data = []
        for reg in registrations:
            tournament = reg.tournament

            # Determine placement
            placement = "Participated"

            # Check if this team won (check winners JSON field)
            if tournament.winners:
                final_round = str(tournament.get_total_rounds())
                if final_round in tournament.winners and tournament.winners[final_round] == reg.id:
                    placement = "1st Place - Winner"

            # Try to get placement from round scores if available
            if placement == "Participated":
                try:
                    # Get total points across all rounds
                    total_score = (
                        RoundScore.objects.filter(tournament=tournament, team=reg).aggregate(
                            total=models.Sum("total_points")
                        )["total"]
                        or 0
                    )

                    if total_score > 0:
                        # Get all teams' total scores for this tournament
                        all_scores = (
                            RoundScore.objects.filter(tournament=tournament)
                            .values("team")
                            .annotate(total=models.Sum("total_points"))
                            .order_by("-total")
                        )

                        # Find this team's position
                        position = 1
                        for score in all_scores:
                            if score["team"] == reg.id:
                                if position == 1:
                                    placement = "1st Place"
                                elif position == 2:
                                    placement = "2nd Place"
                                elif position == 3:
                                    placement = "3rd Place"
                                else:
                                    placement = f"{position}th Place"
                                break
                            position += 1
                except Exception as e:
                    print(f"Error calculating placement: {e}")
                    placement = "Participated"

            # Format date
            date_str = (
                tournament.tournament_end.strftime("%m/%d/%Y")
                if tournament.tournament_end
                else tournament.tournament_start.strftime("%m/%d/%Y")
                if tournament.tournament_start
                else "N/A"
            )

            tournaments_data.append(
                {
                    "id": tournament.id,
                    "name": tournament.title,
                    "date": date_str,
                    "placement": placement,
                    "status": "completed",
                    "tournament_type": tournament.event_mode.lower() if tournament.event_mode else "tournament",
                }
            )

        return Response(tournaments_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def convert_permanent(self, request, pk=None):
        """
        Accept the 48h conversion offer and make the temp team permanent.
        POST /api/accounts/teams/{id}/convert_permanent/
        Only the team captain can call this.
        """
        team = self.get_object()

        if team.captain != request.user:
            return Response({"error": "Only the captain can convert this team"}, status=status.HTTP_403_FORBIDDEN)

        if not team.is_temporary:
            return Response({"error": "This team is already permanent"}, status=status.HTTP_400_BAD_REQUEST)

        if team.conversion_deadline and timezone.now() > team.conversion_deadline:
            return Response({"error": "Conversion window has expired"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if captain already has a permanent team for the same game
        if team.game:
            from accounts.models import TeamMember
            # Normalize game variants (e.g. "Freefire" vs "Free Fire") for conflict check
            game_variants = [team.game]
            normalized = team.game.lower().replace(' ', '')
            if normalized == 'freefire':
                game_variants = ['Free Fire', 'Freefire', 'freefire', 'free fire']
            conflict = Team.objects.filter(
                members__user=request.user,
                game__in=game_variants,
                is_temporary=False,
            ).exclude(id=team.id).first()
            if not conflict:
                # Also check if they are captain of another permanent team for same game
                conflict = Team.objects.filter(
                    captain=request.user,
                    game__in=game_variants,
                    is_temporary=False,
                ).exclude(id=team.id).first()
            if conflict:
                is_captain = conflict.captain == request.user
                return Response({
                    "error": "conflict",
                    "conflict_team_id": conflict.id,
                    "conflict_team_name": conflict.name,
                    "is_captain_of_conflict": is_captain,
                    "message": f"You already have a permanent {team.game} team '{conflict.name}'. You must leave it first before converting this team.",
                }, status=status.HTTP_409_CONFLICT)

        team.is_temporary = False
        team.linked_tournament = None
        team.conversion_deadline = None
        team.save(update_fields=["is_temporary", "linked_tournament", "conversion_deadline"])

        # Auto-kick members who already have a permanent team for the same game
        from accounts.models import Notification
        for membership in TeamMember.objects.filter(team=team).select_related("user"):
            member_user = membership.user
            # Skip the captain — already validated above
            if member_user == request.user:
                continue
            has_conflict = Team.objects.filter(
                members__user=member_user,
                game=team.game,
                is_temporary=False,
            ).exclude(id=team.id).exists()
            if has_conflict:
                TeamMember.objects.filter(team=team, user=member_user).delete()
                if should_notify(member_user, 'tournamentUpdates'):
                    Notification.objects.create(
                        user=member_user,
                        type="general",
                        title="Removed from converted team",
                        message=(
                            f"'{team.name}' was converted to a permanent team, but you already "
                            f"have a permanent {team.game} team. You've been removed from '{team.name}'."
                        ),
                        related_type="team",
                        related_id=team.id,
                    )

        # Mark the notification as read
        Notification.objects.filter(
            user=request.user,
            type="team_conversion_offer",
            related_id=team.id,
        ).update(is_read=True)

        return Response({"success": True, "message": f"Team '{team.name}' is now permanent!"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def decline_conversion(self, request, pk=None):
        """
        Decline the conversion offer and delete the temp team.
        POST /api/accounts/teams/{id}/decline_conversion/
        Only the team captain can call this.
        """
        team = self.get_object()

        if team.captain != request.user:
            return Response({"error": "Only the captain can discard this team"}, status=status.HTTP_403_FORBIDDEN)

        if not team.is_temporary:
            return Response({"error": "This team is not a temporary team"}, status=status.HTTP_400_BAD_REQUEST)

        team_name = team.name
        team.delete()

        return Response({"success": True, "message": f"Team '{team_name}' has been discarded."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="set-member-role")
    def set_member_role(self, request, pk=None):
        """
        PATCH /api/accounts/teams/{team_id}/set-member-role/
        Body: { "member_id": <user_id>, "role": "Assaulter" }
        Captain only.
        """
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can set member roles"}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        role = request.data.get("role", "Member")

        valid_roles = ['IGL', 'Assaulter', 'Support', 'Scout', 'Sniper', 'Rusher', 'Duelist', 'Controller', 'Sentinel', 'Initiator', 'Flex', 'Member']
        if role not in valid_roles:
            return Response({"error": f"Invalid role. Valid: {', '.join(valid_roles)}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = TeamMember.objects.get(team=team, user__id=member_id)
            member.role = role
            member.save()
            return Response({"success": True, "role": role})
        except TeamMember.DoesNotExist:
            return Response({"error": "Member not found in this team"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"], url_path="generate-invite-link")
    def generate_invite_link(self, request, pk=None):
        """
        Generate a shareable invite token link (for WhatsApp, copy-link etc.)
        POST /api/accounts/teams/{team_id}/generate-invite-link/
        Returns: { invite_token: "uuid", join_url: "/join-team/<token>" }
        """
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can generate invite links"}, status=status.HTTP_403_FORBIDDEN)

        invite_token = str(uuid.uuid4())
        TeamJoinRequest.objects.create(
            team=team,
            status="pending",
            request_type="invite",
            invite_type="link",
            invite_token=invite_token,
            invite_expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        return Response({"invite_token": invite_token}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def send_invites(self, request, pk=None):
        """Send team invites via username, email, or phone"""
        team = self.get_object()

        # Only captain can send invites
        if team.captain != request.user:
            return Response({"error": "Only the captain can send invites"}, status=status.HTTP_403_FORBIDDEN)
        if team.is_temporary and team.linked_tournament and team.linked_tournament.registration_end < timezone.now():
            return Response({"error": "Registration has closed. New invites are not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Check team is not full (use game-mode cap for temp teams, 15 for perm teams)
        def get_mode_cap(t):
            mode = None
            if t.is_temporary and t.linked_tournament:
                mode = t.linked_tournament.game_mode
            mode_map = {'5v5': 5, 'Squad': 4, 'Duo': 2, 'Solo': 1}
            return mode_map.get(mode, 15)

        cap = get_mode_cap(team)
        if team.members.count() >= cap:
            return Response({"error": f"Team is full (max {cap} members for this game mode)"}, status=status.HTTP_400_BAD_REQUEST)

        # Get tournament registration for temp team (to link new invites)
        temp_reg = None
        if team.is_temporary:
            try:
                from tournaments.models import TournamentRegistration
                temp_reg = TournamentRegistration.objects.filter(team=team, status='confirmed').first()
            except Exception:
                pass

        invites = request.data.get("invites", [])
        if not invites:
            return Response({"error": "No invites provided"}, status=status.HTTP_400_BAD_REQUEST)

        results = []

        for invite_data in invites:
            invite_type = invite_data.get("type")
            value = invite_data.get("value", "").strip()

            if not value:
                continue

            try:
                if invite_type == "username":
                    # Look up user
                    try:
                        player = User.objects.get(username=value, user_type="player")
                    except User.DoesNotExist:
                        results.append({"value": value, "status": "error", "message": f"Player '{value}' not found"})
                        continue

                    # Check not already a member
                    if TeamMember.objects.filter(team=team, user=player).exists():
                        results.append({"value": value, "status": "error", "message": f"'{value}' is already a team member"})
                        continue

                    # Check not already invited (pending)
                    if TeamJoinRequest.objects.filter(team=team, player=player, status="pending", request_type="invite").exists():
                        results.append({"value": value, "status": "error", "message": f"'{value}' already has a pending invite"})
                        continue

                    # Create invite — link to tournament registration if temp team has open slots
                    # Use actual TeamMember count (not JSON snapshot) to determine available slots
                    invite_token = str(uuid.uuid4())
                    reg_to_link = None
                    if temp_reg:
                        mode_cap = cap
                        current_registered = TeamMember.objects.filter(team=team).count()
                        if current_registered < mode_cap:
                            reg_to_link = temp_reg

                    TeamJoinRequest.objects.create(
                        team=team,
                        player=player,
                        status="pending",
                        request_type="invite",
                        invite_type="username",
                        invite_token=invite_token,
                        invite_expires_at=timezone.now() + timezone.timedelta(days=7),
                        tournament_registration=reg_to_link,
                    )

                    # Pre-add to invited_members_status as pending if slot available
                    if reg_to_link:
                        if not reg_to_link.invited_members_status:
                            reg_to_link.invited_members_status = {}
                        reg_to_link.invited_members_status[value] = {'status': 'pending', 'username': None}
                        reg_to_link.save(update_fields=['invited_members_status', 'updated_at'])

                    # Create in-app notification
                    from accounts.models import Notification
                    if should_notify(player, 'teamInvites'):
                        Notification.objects.create(
                            user=player,
                            type="team_invite",
                            title=f"Team Invite from {team.name}",
                            message=f"{request.user.username} has invited you to join team '{team.name}'.",
                            related_id=team.id,
                            related_type="team",
                        )

                    results.append({"value": value, "status": "success", "message": f"Invite sent to {value}"})

                elif invite_type == "email":
                    # Check if this email belongs to a player already in a permanent team for the same game
                    try:
                        invited_user = User.objects.get(email__iexact=value, user_type="player")
                        if not team.is_temporary:
                            existing_team = TeamMember.objects.filter(
                                user=invited_user,
                                team__is_temporary=False,
                                team__game=team.game,
                            ).select_related("team").first()
                            if existing_team:
                                game_label = team.game or "this game"
                                results.append({
                                    "value": value,
                                    "status": "error",
                                    "message": f"This player is already in a permanent {game_label} team ('{existing_team.team.name}'). They must exit that team before joining a new one.",
                                })
                                continue
                    except User.DoesNotExist:
                        pass  # Unknown email — allow invite, blocked at join time if needed

                    # Create invite with email — link to reg if temp team has open slot
                    invite_token = str(uuid.uuid4())
                    reg_to_link = None
                    if temp_reg:
                        mode_cap = cap
                        current_registered = TeamMember.objects.filter(team=team).count()
                        if current_registered < mode_cap:
                            reg_to_link = temp_reg

                    TeamJoinRequest.objects.create(
                        team=team,
                        status="pending",
                        request_type="invite",
                        invite_type="email",
                        invited_email=value,
                        invite_token=invite_token,
                        invite_expires_at=timezone.now() + timezone.timedelta(days=7),
                        tournament_registration=reg_to_link,
                    )

                    if reg_to_link:
                        if not reg_to_link.invited_members_status:
                            reg_to_link.invited_members_status = {}
                        reg_to_link.invited_members_status[value.lower()] = {'status': 'pending', 'username': None}
                        reg_to_link.save(update_fields=['invited_members_status', 'updated_at'])

                    # Send email (async via Celery if available, sync fallback)
                    try:
                        from scrimverse.email_utils import send_team_invite_email
                        send_team_invite_email(
                            invited_email=value,
                            captain_name=request.user.username,
                            team_name=team.name,
                            invite_token=invite_token,
                            expires_at=(timezone.now() + timezone.timedelta(days=7)).strftime("%B %d, %Y"),
                        )
                    except Exception as e:
                        logger.error(f"Failed to send invite email to {value}: {e}")

                    results.append({"value": value, "status": "success", "message": f"Email invite sent to {value}"})

                elif invite_type == "phone":
                    # Create invite with phone number
                    invite_token = str(uuid.uuid4())
                    TeamJoinRequest.objects.create(
                        team=team,
                        status="pending",
                        request_type="invite",
                        invite_type="phone",
                        phone_number=value,
                        invite_token=invite_token,
                        invite_expires_at=timezone.now() + timezone.timedelta(days=7),
                    )

                    # Send SMS via AWS SNS
                    try:
                        from scrimverse.sms_utils import send_team_invite_sms
                        send_team_invite_sms(
                            phone_number=value,
                            captain_name=request.user.username,
                            team_name=team.name,
                            invite_token=invite_token,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send SMS to {value}: {e}")

                    results.append({"value": value, "status": "success", "message": f"SMS invite sent to {value}"})

                else:
                    results.append({"value": value, "status": "error", "message": f"Invalid invite type: {invite_type}"})

            except Exception as e:
                logger.error(f"Error processing invite {value}: {e}")
                results.append({"value": value, "status": "error", "message": str(e)})

        return Response({"results": results}, status=status.HTTP_200_OK)


# ============================================================================
# TEAM INVITE ENDPOINTS (Invite-Based Registration Flow)
# ============================================================================


class RetrieveInviteDetailsView(APIView):
    """
    Retrieve invite details before accepting/declining.
    GET /api/accounts/invites/<token>/

    Permission: AllowAny (guests can view invite details)
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        """
        Retrieve invite details by token.
        Returns safe public data about the team and tournament.
        """
        try:
            invite = TeamJoinRequest.objects.select_related(
                "team", "tournament_registration__tournament", "tournament_registration__player__user"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if expired
        if invite.invite_expires_at and timezone.now() > invite.invite_expires_at:
            invite.status = "expired"
            invite.save(update_fields=["status"])
            return Response(
                {"error": "This invite has expired", "status": "expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return safe public data
        registration = invite.tournament_registration
        tournament = registration.tournament if registration else None

        # Get captain from team directly if not available via registration
        captain_name = None
        if registration and registration.player:
            captain_name = registration.player.user.username
        elif invite.team.captain:
            captain_name = invite.team.captain.username

        response_data = {
            "team_name": invite.team.name,
            "captain_name": captain_name or "Unknown",
            "tournament_name": tournament.title if tournament else None,
            "status": invite.status,
            "invited_email": invite.invited_email,
            "invite_expires_at": invite.invite_expires_at,
        }

        serializer = TeamInviteDetailSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AcceptInviteView(APIView):
    """
    Accept invite and join the team.
    POST /api/accounts/invites/<token>/accept/

    Permission: IsAuthenticated (user must be logged in)
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, token):
        """
        Accept invite, add user to team, and update registration status.
        """
        user = request.user

        try:
            invite = TeamJoinRequest.objects.select_related(
                "team", "tournament_registration__tournament"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if expired
        if invite.invite_expires_at and timezone.now() > invite.invite_expires_at:
            invite.status = "expired"
            invite.save(update_fields=["status"])
            return Response(
                {"error": "This invite has expired", "status": "expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already accepted — idempotent early return
        if invite.status == 'accepted':
            return Response(
                {"error": "This invite has already been accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if rejected/cancelled
        if invite.status in ('rejected', 'cancelled', 'expired'):
            return Response(
                {"error": f"This invite is no longer valid (status: {invite.status})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate identity matches based on invite type — each mode is independent
        if invite.invite_type == 'phone':
            # Phone invite: verify the logged-in user's phone matches the invited phone
            user_phone_raw = getattr(user, 'phone_number', '') or ''
            clean_user_phone = user_phone_raw.strip().lstrip('+')
            if clean_user_phone.startswith('91') and len(clean_user_phone) > 10:
                clean_user_phone = clean_user_phone[2:]

            invite_phone_raw = (invite.phone_number or '').strip().lstrip('+')
            if invite_phone_raw.startswith('91') and len(invite_phone_raw) > 10:
                invite_phone_raw = invite_phone_raw[2:]

            if clean_user_phone != invite_phone_raw:
                return Response(
                    {"error": "This invite was sent to a different phone number."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Link the now-known user to the invite
            invite.player = user

        elif invite.invite_type == 'username':
            # Username invite: player FK was set at creation time
            if invite.player and invite.player != user:
                return Response(
                    {"error": "This invite was not sent to you."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        else:
            # Email invite (invite_type == 'email' or legacy records without invite_type)
            if not invite.invited_email:
                return Response(
                    {"error": "This invite has no associated email address."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.email.lower() != invite.invited_email.lower():
                logger.warning(
                    f"Email mismatch for invite {token}: user={user.email}, invited={invite.invited_email}"
                )
                return Response(
                    {
                        "error": "Your email does not match the invited email. Please log in with the correct account.",
                        "invited_email": invite.invited_email,
                        "your_email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            invite.player = user

        # Check if tournament registration is still open (for temp team invites)
        if invite.team and invite.team.is_temporary and invite.team.linked_tournament:
            linked_t = invite.team.linked_tournament
            if linked_t.registration_end and timezone.now() > linked_t.registration_end:
                return Response(
                    {"error": "Registration for this tournament has closed. This invite can no longer be accepted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if user is already registered in the same tournament via another team
        if invite.tournament_registration:
            tournament = invite.tournament_registration.tournament
            already_registered = TeamMember.objects.filter(
                user=user,
                team__tournament_registrations__tournament=tournament,
                team__tournament_registrations__status='confirmed',
            ).exclude(team=invite.team).exists()
            if already_registered:
                return Response(
                    {"error": f"You are already registered for '{tournament.title}' with another team."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ACCEPT LOGIC (within atomic transaction)
        from django.db import transaction

        with transaction.atomic():
            # 1. Update TeamJoinRequest — player may have already been set above for phone/email modes
            invite.status = "accepted"
            if not invite.player:
                invite.player = user
            invite.save(update_fields=["status", "player", "updated_at"])

            logger.info(f"Invite {token} accepted by user {user.username}")

            # 2. Add user to team (check if already exists to avoid duplicates)
            team = invite.team
            # First check if user is already in team by user field
            existing_member = TeamMember.objects.filter(team=team, user=user).first()
            if existing_member:
                # User already exists as team member, don't create duplicate
                team_member = existing_member
                logger.info(f"User {user.username} already exists in team {team.name}, not duplicating")
            else:
                # Check if exists by username only (in case user field wasn't set initially)
                existing_by_username = TeamMember.objects.filter(team=team, username=user.username).first()
                if existing_by_username:
                    # Update the user field on existing entry
                    existing_by_username.user = user
                    existing_by_username.save(update_fields=['user'])
                    team_member = existing_by_username
                    logger.info(f"Updated user field for {user.username} in team {team.name}")
                else:
                    # Create new member entry
                    team_member = TeamMember.objects.create(
                        team=team,
                        user=user,
                        username=user.username,
                        is_captain=False,
                    )
                    logger.info(f"Created new team member for {user.username} in team {team.name}")

            # Clean up any duplicate team member entries (keep one, prefer captain)
            all_members = TeamMember.objects.filter(team=team, user=user).order_by('-is_captain', 'id')
            if all_members.count() > 1:
                # Keep the first one (highest is_captain), delete the rest
                to_delete = list(all_members[1:])
                for duplicate in to_delete:
                    logger.info(f"Removing duplicate team member entry for {user.username} in team {team.name}")
                    duplicate.delete()

            logger.info(f"User {user.username} added to team {team.name}")

            # 3. Update TournamentRegistration.invited_members_status
            # Fetch fresh from DB — do NOT use invite.tournament_registration (select_related cache)
            reg_id = invite.tournament_registration_id
            if reg_id:
                from tournaments.models import TournamentRegistration as TReg
                registration = TReg.objects.get(id=reg_id)
            else:
                registration = None
            if registration:
                if not registration.invited_members_status:
                    registration.invited_members_status = {}

                # Determine the contact key based on invite type — each mode is independent
                if invite.invite_type == 'phone':
                    match_key = invite.phone_number or ''
                elif invite.invite_type == 'username':
                    match_key = user.username
                else:
                    # email mode (or legacy records without invite_type)
                    match_key = invite.invited_email or ''

                if match_key:
                    for contact_key, member_status in registration.invited_members_status.items():
                        if contact_key.lower() == match_key.lower():
                            member_status["status"] = "accepted"
                            member_status["username"] = user.username
                            break

                # Also update team_members JSON — mark this player as is_registered=True
                player_profile = getattr(user, 'player_profile', None)
                player_id = player_profile.id if player_profile else None
                if registration.team_members is None:
                    registration.team_members = []
                member_found = False
                updated_members = []
                for member in registration.team_members:
                    member_matched = False
                    if invite.invite_type == 'phone' and member.get('phone') == invite.phone_number:
                        member_matched = True
                    elif invite.invite_type == 'username' and member.get('username', '').lower() == user.username.lower():
                        member_matched = True
                    elif invite.invite_type == 'email' and member.get('email', '').lower() == (invite.invited_email or '').lower():
                        member_matched = True
                    if member_matched:
                        member = dict(member)
                        member['username'] = user.username
                        member['player_id'] = player_id
                        member['is_registered'] = True
                        member_found = True
                    updated_members.append(member)
                registration.team_members = updated_members
                if not member_found:
                    # Post-registration invite — no placeholder was pre-added; append now
                    # Must reassign (not just .append) so Django JSONField detects the change
                    registration.team_members = registration.team_members + [{
                        'username': user.username,
                        'player_id': player_id,
                        'is_registered': True,
                    }]

                registration.save(update_fields=["invited_members_status", "team_members", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {match_key} accepted by {user.username}"
                )

        return Response(
            {
                "success": True,
                "message": f"Successfully accepted invite and joined {team.name}!",
                "team_id": team.id,
                "team_name": team.name,
            },
            status=status.HTTP_200_OK,
        )


class DeclineInviteView(APIView):
    """
    Decline invite without joining the team.
    POST /api/accounts/invites/<token>/decline/

    Permission: AllowAny (allow declining without login)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        """
        Decline invite and mark as rejected.
        """
        try:
            invite = TeamJoinRequest.objects.select_related(
                "tournament_registration__tournament"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # DECLINE LOGIC
        from django.db import transaction

        with transaction.atomic():
            # 1. Update TeamJoinRequest status
            invite.status = "rejected"
            invite.save(update_fields=["status", "updated_at"])

            logger.info(f"Invite {token} declined")

            # 2. Update TournamentRegistration.invited_members_status
            registration = invite.tournament_registration
            if registration:
                if not registration.invited_members_status:
                    registration.invited_members_status = {}

                # Determine the contact key based on invite type — each mode is independent
                if invite.invite_type == 'phone':
                    match_key = invite.phone_number or ''
                elif invite.invite_type == 'username':
                    match_key = invite.player.username if invite.player else ''
                else:
                    # email mode (or legacy records without invite_type)
                    match_key = invite.invited_email or ''

                if match_key:
                    for contact_key, member_status in registration.invited_members_status.items():
                        if contact_key.lower() == match_key.lower():
                            member_status["status"] = "declined"
                            # username stays None since they declined
                            break

                registration.save(update_fields=["invited_members_status", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {match_key} declined invite"
                )

        return Response(
            {
                "success": True,
                "message": "Invite declined successfully",
            },
            status=status.HTTP_200_OK,
        )
