"""
API views for Match Management (Scrim-aware)
Handles match lifecycle: room details, start/end, score submission
"""
from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile

from .models import Match, MatchScore, Tournament, TournamentRegistration


class IsHostUser(permissions.BasePermission):
    """Permission class for Host users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "host"


class UpdateMatchRoomDetailsView(generics.GenericAPIView):
    """
    Update room ID and password for a match
    PATCH /api/tournaments/<tournament_id>/matches/<match_id>/room/
    Body: {
        "room_id": "ABC123",
        "room_password": "pass456"
    }
    """

    permission_classes = [IsHostUser]

    def patch(self, request, tournament_id, match_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check if room details can be edited
        if not match.can_edit_room_details():
            return Response({"error": "Cannot edit room details after match has started"}, status=400)

        room_id = request.data.get("room_id")
        room_password = request.data.get("room_password")

        # For scrims, both fields are required
        if tournament.event_mode == "SCRIM":
            if not room_id or not room_password:
                return Response({"error": "Both Room ID and Password are required for scrims"}, status=400)

        # Update match
        if room_id:
            match.match_id = room_id
        if room_password:
            match.match_password = room_password

        match.save(update_fields=["match_id", "match_password"])

        return Response(
            {
                "message": "Room details updated successfully",
                "match_id": match.id,
                "room_id": match.match_id,
                "status": match.status,
            }
        )


class StartMatchView(generics.GenericAPIView):
    """
    Start a match (WAITING → LIVE)
    POST /api/tournaments/<tournament_id>/matches/<match_id>/start/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check if match can be started
        can_start, message = match.can_start_match()
        if not can_start:
            return Response({"error": message}, status=400)

        # Start the match
        match.status = "live"
        match.started_at = timezone.now()
        match.save(update_fields=["status", "started_at"])

        return Response(
            {
                "message": "Match started successfully",
                "match_id": match.id,
                "match_number": match.match_number,
                "status": match.status,
                "started_at": match.started_at,
                "room_id": match.match_id,
                "room_password": match.match_password,
            }
        )


class EndMatchView(generics.GenericAPIView):
    """
    End a match (LIVE → COMPLETED)
    POST /api/tournaments/<tournament_id>/matches/<match_id>/end/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check if match can be ended
        can_end, message = match.can_end_match()
        if not can_end:
            return Response({"error": message}, status=400)

        # End the match
        match.status = "completed"
        match.ended_at = timezone.now()
        match.save(update_fields=["status", "ended_at"])

        # For scrims, recalculate aggregate standings
        if tournament.event_mode == "SCRIM":
            self._update_scrim_standings(tournament)

        return Response(
            {
                "message": "Match ended successfully",
                "match_id": match.id,
                "match_number": match.match_number,
                "status": match.status,
                "ended_at": match.ended_at,
            }
        )

    def _update_scrim_standings(self, tournament):
        """Calculate aggregate standings across all completed matches"""
        from django.db.models import Sum

        # Get all teams
        teams = tournament.registrations.filter(status="confirmed")

        standings = []
        for team in teams:
            # Sum points across all matches
            total_points = (
                MatchScore.objects.filter(match__group__tournament=tournament, team=team).aggregate(
                    total=Sum("total_points")
                )["total"]
                or 0
            )

            standings.append({"team_id": team.id, "team_name": team.team_name, "total_points": total_points})

        # Sort by points
        standings.sort(key=lambda x: x["total_points"], reverse=True)

        # Store in tournament metadata (optional)
        if not hasattr(tournament, "scrim_standings"):
            tournament.scrim_standings = {}
        tournament.scrim_standings = standings
        tournament.save(update_fields=["scrim_standings"])


class CancelMatchView(generics.GenericAPIView):
    """
    Cancel a live match (LIVE → WAITING) - Emergency rollback
    POST /api/tournaments/<tournament_id>/matches/<match_id>/cancel/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check if match can be cancelled
        can_cancel, message = match.can_cancel_match()
        if not can_cancel:
            return Response({"error": message}, status=400)

        # Cancel the match
        match.status = "waiting"
        match.started_at = None
        match.save(update_fields=["status", "started_at"])

        return Response(
            {
                "message": "Match cancelled and reset to waiting",
                "match_id": match.id,
                "match_number": match.match_number,
                "status": match.status,
            }
        )


class SubmitMatchScoresView(generics.GenericAPIView):
    """
    Submit or update scores for a match
    POST /api/tournaments/<tournament_id>/matches/<match_id>/scores/
    Body: {
        "scores": [
            {
                "team_id": 123,
                "kills": 15,
                "placement": 1
            },
            ...
        ]
    }
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, match_id):
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check if scores can be edited
        if not match.can_edit_scores():
            return Response({"error": "Cannot edit scores for this match (locked or grace period expired)"}, status=400)

        scores_data = request.data.get("scores", [])
        if not scores_data:
            return Response({"error": "No scores provided"}, status=400)

        # Placement points mapping (BGMI style)
        placement_points_map = {
            1: 10,
            2: 6,
            3: 5,
            4: 4,
            5: 3,
            6: 2,
            7: 1,
            8: 1,
            9: 0,
            10: 0,
            11: 0,
            12: 0,
            13: 0,
            14: 0,
            15: 0,
            16: 0,
        }

        created_scores = []
        for score_data in scores_data:
            team_id = score_data.get("team_id")
            kills = score_data.get("kills", 0)
            placement = score_data.get("placement", 16)

            try:
                team = TournamentRegistration.objects.get(id=team_id, tournament=tournament, status="confirmed")
            except TournamentRegistration.DoesNotExist:
                return Response({"error": f"Team {team_id} not found or not confirmed"}, status=400)

            # Calculate points
            kill_points = int(kills)
            position_points = placement_points_map.get(int(placement), 0)

            # Create or update score
            match_score, created = MatchScore.objects.update_or_create(
                match=match,
                team=team,
                defaults={
                    "kill_points": kill_points,
                    "position_points": position_points,
                    # total_points calculated automatically in model save()
                },
            )

            created_scores.append(
                {
                    "team_id": team.id,
                    "team_name": team.team_name,
                    "kills": kill_points,
                    "placement": placement,
                    "position_points": position_points,
                    "total_points": match_score.total_points,
                }
            )

        return Response(
            {
                "message": f"Scores submitted for {len(created_scores)} teams",
                "match_id": match.id,
                "match_number": match.match_number,
                "scores": created_scores,
            }
        )


class GetMatchDetailsView(generics.GenericAPIView):
    """
    Get match details including room info and scores
    GET /api/tournaments/<tournament_id>/matches/<match_id>/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, tournament_id, match_id):
        try:
            tournament = Tournament.objects.get(id=tournament_id)
            match = Match.objects.get(id=match_id, group__tournament=tournament)
        except (Tournament.DoesNotExist, Match.DoesNotExist):
            return Response({"error": "Tournament or Match not found"}, status=404)

        # Check user role
        is_host = request.user.user_type == "host" and tournament.host.user == request.user
        is_player = request.user.user_type == "player"

        # Room details visibility
        show_room_details = False
        if is_host:
            show_room_details = True  # Host always sees room details
        elif is_player:
            # Check if player is registered and confirmed for this tournament/scrim
            is_registered = TournamentRegistration.objects.filter(
                tournament=tournament, player__user=request.user, status="confirmed"
            ).exists()

            # Players see room details when waiting or live, if registered
            if is_registered and match.status in ["waiting", "live"]:
                show_room_details = True

        # Build response
        response_data = {
            "match_id": match.id,
            "match_number": match.match_number,
            "status": match.status,
            "started_at": match.started_at,
            "ended_at": match.ended_at,
            "can_edit_room": match.can_edit_room_details() if is_host else False,
            "can_edit_scores": match.can_edit_scores() if is_host else False,
        }

        if show_room_details:
            response_data["room_id"] = match.match_id
            response_data["room_password"] = match.match_password

        # Include scores
        scores = MatchScore.objects.filter(match=match).select_related("team")
        response_data["scores"] = [
            {
                "team_id": score.team.id,
                "team_name": score.team.team_name,
                "kills": score.kill_points,
                "placement_points": score.position_points,
                "total_points": score.total_points,
            }
            for score in scores
        ]

        return Response(response_data)
