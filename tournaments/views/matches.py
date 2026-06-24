"""
Match management views.
Handles starting, ending, scoring matches, and fetching team players.
"""
import logging

from django.utils import timezone

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile, Notification, PlayerProfile, TeamMember, User
from tournaments.models import Group, Match, MatchScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger("tournaments")


class StartMatchView(generics.GenericAPIView):
    """
    Start a match (set match ID and password)
    POST /api/tournaments/<tournament_id>/groups/<group_id>/matches/start/
    Body: {
        "match_number": 1,
        "match_id": "ROOM123",
        "match_password": "pass456"
    }
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, group_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        group = Group.objects.get(id=group_id, tournament=tournament)

        match_number = request.data.get("match_number")
        match_id = request.data.get("match_id", "")
        match_password = request.data.get("match_password", "")

        if not match_number:
            return Response({"error": "match_number is required"}, status=400)

        # Validate match_id based on game requirements
        if not match_id:
            return Response({"error": "match_id is required"}, status=400)

        # Validate password requirement based on game
        requires_password = tournament.requires_password()
        if requires_password and not match_password:
            return Response(
                {"error": f"match_password is required for {tournament.game_name} tournaments"},
                status=400
            )

        try:
            match = Match.objects.get(group=group, match_number=match_number)
        except Match.DoesNotExist:
            return Response({"error": f"Match {match_number} not found in {group.group_name}"}, status=404)

        if match.status == "completed":
            return Response({"error": "Match is already completed"}, status=400)

        # Enforce sequential match flow: can only start match N if match N-1 is completed
        # Note: Scores are OPTIONAL and can be entered later - don't block match start on missing scores
        if match_number > 1:
            previous_match = Match.objects.filter(group=group, match_number=match_number - 1).first()

            if previous_match:
                if previous_match.status != "completed":
                    return Response(
                        {
                            "error": f"Cannot start Match {match_number}. Match {match_number - 1} must be completed first."  # noqa: E501
                        },
                        status=400,
                    )

        # Parse optional scheduled credential release time
        # Preserve existing release time if the host doesn't explicitly send a new one
        credential_release_time = match.credential_release_time
        raw_release = request.data.get("credential_release_time")
        if raw_release:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(raw_release)
            if parsed:
                credential_release_time = parsed if parsed.tzinfo else timezone.make_aware(parsed)

        # Update match details
        match.match_id = match_id
        match.match_password = match_password if requires_password else ""
        match.status = "ongoing"
        match.started_at = timezone.now()
        match.credential_release_time = credential_release_time
        match.save()

        # Update group status to ongoing if it was waiting
        if group.status == "waiting":
            group.status = "ongoing"
            group.save(update_fields=["status"])

        # Send credential notification immediately only if no scheduled release time
        if not credential_release_time:
            group_registrations = TournamentRegistration.objects.filter(
                tournament_groups=group
            ).select_related("team")
            cred_notifications = []
            for reg in group_registrations:
                member_user_ids = TeamMember.objects.filter(
                    team=reg.team, user__isnull=False
                ).values_list("user_id", flat=True)
                for user_id in member_user_ids:
                    cred_notifications.append(
                        Notification(
                            user_id=user_id,
                            type="credential_release",
                            related_id=tournament.id,
                            related_type="tournament",
                            title="Room ID is ready!",
                            message=(
                                f"Room ID & Password for '{tournament.title}' Match {match.match_number} "
                                f"({group.group_name}) are now available. Check your ID & Passwords tab."
                            ),
                            is_read=False,
                        )
                    )
            if cred_notifications:
                Notification.objects.bulk_create(cred_notifications, ignore_conflicts=True)

        # Build response
        response_match = {
            "id": match.id,
            "match_number": match.match_number,
            "match_id": match.match_id,
            "status": match.status,
            "started_at": match.started_at,
        }

        # Only include password in response if required
        if requires_password:
            response_match["match_password"] = match.match_password

        logger.debug(
            f"Match {match_number} started successfully - Tournament: {tournament.title} ({tournament.id}), Group: {group.id}, Match: {match.id}"  # noqa E501
        )

        return Response(
            {
                "message": f"Match {match_number} started successfully",
                "match": response_match,
            }
        )


class UpdateMatchCredentialsView(generics.GenericAPIView):
    """
    Update match credentials (Room ID / Password) without changing match status.
    PATCH /api/tournaments/<tournament_id>/matches/<match_id>/credentials/
    Body: { "match_id": "ROOM123", "match_password": "pass456" }
    """

    permission_classes = [IsHostUser]

    def patch(self, request, tournament_id, match_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        try:
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except Match.DoesNotExist:
            return Response({"error": "Match not found"}, status=404)

        if match.status == "completed":
            return Response({"error": "Cannot update credentials for a completed match"}, status=400)

        match_room_id = request.data.get("match_id", match.match_id)
        match_password = request.data.get("match_password", match.match_password)

        if not match_room_id:
            return Response({"error": "match_id is required"}, status=400)

        # Parse optional credential release time update
        raw_release = request.data.get("credential_release_time", "UNCHANGED")
        if raw_release != "UNCHANGED":
            if raw_release:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(raw_release)
                if parsed:
                    match.credential_release_time = parsed if parsed.tzinfo else timezone.make_aware(parsed)
            else:
                match.credential_release_time = None

        is_first_release = not match.match_id  # credentials being set for the first time
        match.match_id = match_room_id
        match.match_password = match_password
        match.save(update_fields=["match_id", "match_password", "credential_release_time"])

        # Send credential notification only to players in this match's group
        if is_first_release:
            group = match.group
            group_registrations = TournamentRegistration.objects.filter(
                tournament_groups=group
            ).select_related("team")
            cred_notifications = []
            for reg in group_registrations:
                member_user_ids = TeamMember.objects.filter(
                    team=reg.team, user__isnull=False
                ).values_list("user_id", flat=True)
                for user_id in member_user_ids:
                    cred_notifications.append(
                        Notification(
                            user_id=user_id,
                            type="credential_release",
                            related_id=tournament.id,
                            related_type="tournament",
                            title="Room ID is ready!",
                            message=(
                                f"Room ID & Password for '{tournament.title}' Match {match.match_number} "
                                f"({group.group_name}) are now available. Check your ID & Passwords tab."
                            ),
                            is_read=False,
                        )
                    )
            if cred_notifications:
                Notification.objects.bulk_create(cred_notifications, ignore_conflicts=True)

        return Response({
            "message": "Match credentials updated",
            "match": {
                "id": match.id,
                "match_number": match.match_number,
                "match_id": match.match_id,
                "match_password": match.match_password,
                "status": match.status,
            }
        })


class EndMatchView(generics.GenericAPIView):
    """
    End a match
    POST /api/tournaments/<tournament_id>/matches/<match_id>/end/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        try:
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except Match.DoesNotExist:
            return Response({"error": "Match not found"}, status=404)

        if match.status != "ongoing":
            return Response({"error": "Match is not currently ongoing"}, status=400)

        match.status = "completed"
        match.ended_at = timezone.now()
        match.save()

        logger.debug(
            f"Match {match.match_number} ended successfully - Tournament: {tournament.title} ({tournament.id}), Match: {match.id}"  # noqa E501
        )

        return Response(
            {
                "message": f"Match {match.match_number} ended successfully",
                "match": {
                    "id": match.id,
                    "match_number": match.match_number,
                    "status": match.status,
                    "ended_at": match.ended_at,
                },
            }
        )


class SubmitMatchScoresView(generics.GenericAPIView):
    """
    Submit scores for all teams in a match
    POST /api/tournaments/<tournament_id>/matches/<match_id>/scores/
    Body: {
        "scores": [
            {"team_id": 12, "wins": 1, "position_points": 10, "kill_points": 8},
            {"team_id": 13, "wins": 0, "position_points": 5, "kill_points": 12}
        ]
    }
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        try:
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except Match.DoesNotExist:
            return Response({"error": "Match not found"}, status=404)

        if match.status != "completed":
            return Response({"error": "Match must be completed before submitting scores"}, status=400)

        # Check if scores already exist (prevent re-editing)
        existing_scores = MatchScore.objects.filter(match=match).count()
        if existing_scores > 0:
            return Response(
                {"error": "Scores have already been submitted for this match and cannot be edited"}, status=400
            )

        scores_data = request.data.get("scores", [])
        if not scores_data or not isinstance(scores_data, list):
            return Response({"error": "scores must be a list"}, status=400)

        # Save scores
        logger.debug(f"Processing {len(scores_data)} score entries for match {match_id}")
        created_count = 0
        for score_entry in scores_data:
            team_id = score_entry.get("team_id")
            wins = int(score_entry.get("wins", 0))
            position_points = int(score_entry.get("position_points", 0))
            kill_points = int(score_entry.get("kill_points", 0))

            if not team_id:
                continue

            try:
                team = TournamentRegistration.objects.get(id=team_id, tournament=tournament)
            except TournamentRegistration.DoesNotExist:
                continue

            MatchScore.objects.create(
                match=match, team=team, wins=wins, position_points=position_points, kill_points=kill_points
            )
            created_count += 1

        # For 5v5 games: Determine match winner after scores are submitted
        is_5v5_game = tournament.is_5v5_game()
        if is_5v5_game:
            match.determine_winner()
            logger.debug(f"Match winner determined - Match: {match_id}, Winner: {match.winner.team_name if match.winner else 'None'}")

        # Clear room credentials so players can no longer see old room details
        match.match_id = ""
        match.match_password = ""
        match.save(update_fields=["match_id", "match_password"])

        # Update RoundScore aggregates
        logger.debug(f"Calculating round scores - Tournament: {tournament.id}, Round: {match.group.round_number}")
        TournamentGroupService.calculate_round_scores(tournament, match.group.round_number)

        # Check if all matches in the group are completed with scores
        group = match.group
        logger.info(
            f"Match scores submitted - Match: {match_id}, Scores: {created_count}, Group: {group.group_name}"
        )
        all_matches_scored = all(m.scores.exists() for m in group.matches.filter(status="completed"))

        if all_matches_scored and group.matches.filter(status="completed").count() == group.matches.count():
            group.status = "completed"

            # For 5v5 games: Determine group winner after all matches are completed
            if is_5v5_game:
                group.determine_group_winner()
                logger.debug(f"Group winner determined - Group: {group.group_name}, Winner: {group.winner.team_name if group.winner else 'None'}")

            group.save(update_fields=["status"])

        # Notify all teams in this group that match scores have been entered
        try:
            group_registrations = TournamentRegistration.objects.filter(
                tournament_groups=group
            ).select_related("team")
            notifications = []
            match_label = f"Match {match.match_number}" if match.match_number else "A match"
            for reg in group_registrations:
                member_user_ids = TeamMember.objects.filter(
                    team=reg.team, user__isnull=False
                ).values_list("user_id", flat=True)
                for user_id in member_user_ids:
                    notifications.append(
                        Notification(
                            user_id=user_id,
                            type="points_entered",
                            title="Points Updated",
                            message=f"{match_label} scores have been submitted for {tournament.title}. Check your Points Table!",
                            related_id=tournament.id,
                            related_type="tournament",
                        )
                    )
            if notifications:
                Notification.objects.bulk_create(notifications)
        except Exception as e:
            logger.error(f"Failed to send points_entered notifications: {e}", exc_info=True)

        return Response(
            {
                "message": f"Scores submitted successfully for {created_count} teams",
                "match_id": match.id,
                "match_number": match.match_number,
                "group_completed": group.status == "completed",
            }
        )


class GetTeamPlayersView(generics.GenericAPIView):
    """
    Get all players/members for a specific team registration in a tournament
    GET /api/tournaments/<tournament_id>/teams/<registration_id>/players/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, tournament_id, registration_id):
        try:
            tournament = Tournament.objects.get(id=tournament_id)
            registration = TournamentRegistration.objects.select_related("team", "player__user").get(
                id=registration_id, tournament=tournament
            )
        except (Tournament.DoesNotExist, TournamentRegistration.DoesNotExist):
            return Response({"error": "Tournament or team registration not found"}, status=404)

        players_data = []

        # Try to get players from team_members JSON field first
        team_members = registration.team_members or []

        if team_members:
            # Enrich with player profile data from team_members JSON
            for member in team_members:
                # team_members may be stored as a list of dicts OR as a list of usernames (strings).
                player_profile = None

                # If member is a dict, try to read id/username keys
                if isinstance(member, dict):
                    player_id = member.get("id")
                    username = member.get("username")

                    if player_id:
                        try:
                            player_profile = PlayerProfile.objects.select_related("user").get(id=player_id)
                        except PlayerProfile.DoesNotExist:
                            player_profile = None

                    if not player_profile and username:
                        try:
                            user = User.objects.get(username=username, user_type="player")
                            player_profile = user.player_profile
                        except (User.DoesNotExist, PlayerProfile.DoesNotExist, AttributeError):
                            player_profile = None

                # If member is a string, treat it as username
                elif isinstance(member, str):
                    username = member
                    try:
                        user = User.objects.get(username=username, user_type="player")
                        player_profile = user.player_profile
                    except (User.DoesNotExist, PlayerProfile.DoesNotExist, AttributeError):
                        player_profile = None

                # If we found a profile, append enriched data
                if player_profile:
                    players_data.append(
                        {
                            "id": player_profile.id,
                            "user_id": player_profile.user.id,
                            "username": player_profile.user.username,
                            "preferred_games": player_profile.preferred_games,
                            "bio": player_profile.bio,
                            "profile_picture": (
                                player_profile.user.profile_picture.url if player_profile.user.profile_picture else None
                            ),
                            "is_captain": player_profile.id == registration.player_id,
                        }
                    )
                    logger.debug(f"Team members found - Team ID: {registration.team_id}, Players: {players_data}")

        # team_members is the authoritative snapshot for this specific tournament registration.
        # No fallback to the Team model — it may contain members not part of this registration.

        return Response(
            {
                "tournament_id": tournament.id,
                "registration_id": registration.id,
                "team_name": registration.team_name,
                "players": players_data,
                "total_players": len(players_data),
            }
        )
