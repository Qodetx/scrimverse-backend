import logging

from django.db import models
from django.utils import timezone

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, User
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
                ).distinct()
            else:
                queryset = Team.objects.all()

            # Apply search filter if provided
            if search:
                queryset = queryset.filter(name__icontains=search)

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

        # Check if user is already in a PERMANENT team (temporary teams are allowed)
        existing_membership = TeamMember.objects.filter(
            user=self.request.user, team__is_temporary=False  # Only check for permanent teams
        ).exists()
        if existing_membership:
            raise ValidationError({"error": "You are already a member of a team. Leave your current team first."})

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

        # Check if user is already in another PERMANENT team
        if TeamMember.objects.filter(user=user, team__is_temporary=False).exclude(team=team).exists():
            return Response(
                {"error": f"{username} is already a member of another team"}, status=status.HTTP_400_BAD_REQUEST
            )

        member = TeamMember.objects.create(team=team, username=username, user=user, is_captain=False)

        logger.debug(f"Member added - Team: {team.id}, Member: {username}, User ID: {user.id}")

        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can remove members"}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not member:
            return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        if member.user == team.captain:
            return Response(
                {"error": "Cannot remove the captain. Transfer captaincy first."}, status=status.HTTP_400_BAD_REQUEST
            )

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transfer_captaincy(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response(
                {"error": "Only the current captain can transfer captaincy"}, status=status.HTTP_403_FORBIDDEN
            )

        member_id = request.data.get("member_id")
        new_captain_member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not new_captain_member or not new_captain_member.user:
            return Response(
                {"error": "New captain must be a registered user in the team"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Update team captain
        team.captain = new_captain_member.user
        team.save()

        # Update flags
        TeamMember.objects.filter(team=team).update(is_captain=False)
        new_captain_member.is_captain = True
        new_captain_member.save()

        return Response(TeamSerializer(team).data)

    @action(detail=True, methods=["post"])
    def request_join(self, request, pk=None):
        """Player requests to join a team"""
        team = self.get_object()

        logger.debug(f"Join request - Team: {team.id}, Player: {request.user.id}")

        # Check if user is already in a PERMANENT team
        if TeamMember.objects.filter(user=request.user, team__is_temporary=False).exists():
            return Response({"error": "You are already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if team is full
        if team.members.count() >= 15:
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update join request
        join_request, created = TeamJoinRequest.objects.get_or_create(
            team=team, player=request.user, defaults={"status": "pending", "request_type": "request"}
        )

        if not created:
            if join_request.status == "rejected":
                join_request.status = "pending"
                join_request.request_type = "request"
                join_request.save()
            elif join_request.request_type == "invite" and join_request.status == "pending":
                return Response(
                    {"message": "You already have a pending invite from this team"}, status=status.HTTP_400_BAD_REQUEST
                )

        logger.debug(
            f"Join request created - Team: {team.id}, Player: {request.user.username}, Status: {join_request.status}"
        )

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

        player_id = request.data.get("player_id")
        if not player_id:
            return Response({"error": "player_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            player = User.objects.get(id=player_id, user_type="player")
        except User.DoesNotExist:
            return Response({"error": "Player not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if player is already in a PERMANENT team
        if TeamMember.objects.filter(user=player, team__is_temporary=False).exists():
            return Response({"error": "Player is already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

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
            # Check if player is already in a team
            if TeamMember.objects.filter(user=request.user, team__is_temporary=False).exists():
                return Response({"error": "You are already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if team is full
            if team.members.count() >= 15:
                return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

            # Add member
            TeamMember.objects.create(team=team, user=request.user, username=request.user.username, is_captain=False)
            invite.status = "accepted"
            invite.save()

            return Response({"message": "Invitation accepted"}, status=status.HTTP_200_OK)
        else:
            invite.status = "rejected"
            invite.save()

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

        response_data = {
            "team_name": invite.team.name,
            "captain_name": registration.player.user.username if registration else "Unknown",
            "tournament_name": tournament.title if tournament else "Unknown",
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

        # Validate email matches
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

        # ACCEPT LOGIC (within atomic transaction)
        from django.db import transaction

        with transaction.atomic():
            # 1. Update TeamJoinRequest
            invite.status = "accepted"
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
            registration = invite.tournament_registration
            if registration:
                if not registration.invited_members_status:
                    registration.invited_members_status = {}

                # Find the entry matching this email and update it
                for email_key, member_status in registration.invited_members_status.items():
                    if email_key.lower() == invite.invited_email.lower():
                        member_status["status"] = "accepted"
                        member_status["username"] = user.username
                        break

                registration.save(update_fields=["invited_members_status", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {invite.invited_email} accepted by {user.username}"
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

                # Find the entry matching this email and update it
                for email_key, member_status in registration.invited_members_status.items():
                    if email_key.lower() == invite.invited_email.lower():
                        member_status["status"] = "declined"
                        # username stays None since they declined
                        break

                registration.save(update_fields=["invited_members_status", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {invite.invited_email} declined invite"
                )

        return Response(
            {
                "success": True,
                "message": "Invite declined successfully",
                "invited_email": invite.invited_email,
            },
            status=status.HTTP_200_OK,
        )
