import logging

from django.core.cache import cache

from rest_framework import generics
from rest_framework.response import Response

from accounts.models import HostProfile, Notification, TeamMember
from tournaments.models import RoundScore, Tournament, TournamentRegistration
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger(__name__)


class StartRoundView(generics.GenericAPIView):
    """
    Start a specific round
    POST /api/tournaments/<tournament_id>/start-round/<round_number>/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, round_number):
        logger.debug(
            f"Start round request - Tournament: {tournament_id}, Round: {round_number}, Host: {request.user.id}"
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        # Validate round number
        if round_number < 1 or round_number > len(tournament.rounds):
            return Response(
                {"error": f"Invalid round number. Tournament has {len(tournament.rounds)} rounds."}, status=400
            )

        # Check if previous round is completed (if not first round)
        if round_number > 1:
            prev_round_status = tournament.round_status.get(str(round_number - 1))
            if prev_round_status != "completed":
                return Response(
                    {"error": f"Round {round_number - 1} must be completed before starting round {round_number}"},
                    status=400,
                )

        # Initialize round_status if needed
        if not tournament.round_status:
            tournament.round_status = {}

        round_key = str(round_number)
        existing_status = tournament.round_status.get(round_key)
        was_preconfigured = (
            isinstance(existing_status, dict) and existing_status.get("status") == "pre_configured"
        )

        # Set current round and status
        tournament.current_round = round_number
        tournament.round_status[round_key] = "ongoing"

        # Initialize selected_teams for this round if not exists
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        if round_key not in tournament.selected_teams:
            tournament.selected_teams[round_key] = []

        tournament.save(update_fields=["current_round", "round_status", "selected_teams"])
        cache.delete("tournaments:list:all")

        logger.info(f"Round started - Tournament: {tournament.id}, Round: {round_number}, Status: ongoing")

        # If groups were pre-configured, now that the round is truly starting send slot_list notifications
        if was_preconfigured:
            try:
                registrations = TournamentRegistration.objects.filter(
                    tournament=tournament, status="confirmed"
                ).select_related("team")
                notifications = []
                for reg in registrations:
                    member_user_ids = TeamMember.objects.filter(
                        team=reg.team, user__isnull=False
                    ).values_list("user_id", flat=True)
                    for user_id in member_user_ids:
                        notifications.append(
                            Notification(
                                user_id=user_id,
                                type="slot_list",
                                title="Groups Assigned",
                                message=f"Groups have been locked for {tournament.title}. Check your slot list!",
                                related_id=tournament.id,
                                related_type="tournament",
                            )
                        )
                if notifications:
                    Notification.objects.bulk_create(notifications)
                    logger.info(
                        f"Slot list notifications sent on round start (pre-configured) - "
                        f"Tournament: {tournament.id}, Round: {round_number}, Players notified: {len(notifications)}"
                    )
            except Exception as e:
                logger.error(f"Failed to send slot list notifications on round start: {e}", exc_info=True)

        return Response(
            {
                "message": f"Round {round_number} started",
                "current_round": tournament.current_round,
                "round_status": tournament.round_status,
            }
        )


class SubmitRoundScoresView(generics.GenericAPIView):
    """
    Host submits scores for teams in a round.
    POST /api/tournaments/<tournament_id>/submit-scores/
    Body: [
      {"team_id": 12, "position_points": 10, "kill_points": 8},
      {"team_id": 13, "position_points": 5, "kill_points": 12}
    ]
    Automatically selects top qualifying teams.
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        logger.debug(f"Submit round scores request - Tournament: {tournament_id}, Host: {request.user.id}")

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        round_num = tournament.current_round

        if round_num == 0:
            return Response({"error": "No active round"}, status=400)

        scores_data = request.data
        if not isinstance(scores_data, list):
            return Response({"error": "Invalid data format"}, status=400)

        # Save scores
        for entry in scores_data:
            team_id = entry.get("team_id")
            position_points = int(entry.get("position_points", 0))
            kill_points = int(entry.get("kill_points", 0))
            team = TournamentRegistration.objects.get(id=team_id, tournament=tournament)
            RoundScore.objects.update_or_create(
                tournament=tournament,
                round_number=round_num,
                team=team,
                defaults={"position_points": position_points, "kill_points": kill_points},
            )

        # Auto select top N teams
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)
        qualifying_teams = int(round_config.get("qualifying_teams") or 0)
        all_scores = RoundScore.objects.filter(tournament=tournament, round_number=round_num).order_by("-total_points", "-position_points")

        selected_team_ids = list(all_scores.values_list("team_id", flat=True)[:qualifying_teams])
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        tournament.selected_teams[str(round_num)] = selected_team_ids
        tournament.save(update_fields=["selected_teams"])

        logger.info(
            f"Round scores submitted - Tournament: {tournament.id}, Round: {round_num}, Teams scored: {len(scores_data)}, Top teams: {len(selected_team_ids)}"  # noqa E501
        )

        return Response(
            {
                "message": f"Scores submitted successfully. Top {qualifying_teams} teams auto-selected.",
                "selected_teams": selected_team_ids,
            }
        )


class EndRoundView(generics.GenericAPIView):
    """
    End current round and move to next
    POST /api/tournaments/<tournament_id>/end-round/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        round_num = tournament.current_round
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        # For ending round: check if it's final round (no qualifying_teams) or regular round
        qualifying_teams = round_config.get("qualifying_teams")
        max_teams = int(round_config.get("max_teams") or 0)
        is_final_round = not qualifying_teams or int(qualifying_teams) == 0

        selected_count = len(tournament.selected_teams.get(str(round_num), []))

        # Final round: must have winner selected, not just teams
        if is_final_round:
            round_key = str(round_num)
            winner = tournament.winners.get(round_key) if tournament.winners else None
            if not winner:
                return Response({"error": "Final round requires a winner to be selected before ending"}, status=400)
        else:
            # Regular round: must select exactly qualifying_teams (not max_teams)
            required_teams = int(qualifying_teams) if qualifying_teams else max_teams
            if selected_count != required_teams:
                return Response(
                    {"error": f"Must select exactly {required_teams} teams. " f"Currently selected: {selected_count}"},
                    status=400,
                )

        # Mark current round as completed
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status[str(round_num)] = "completed"

        # Find next round - handle both int and string round numbers
        next_round = None
        next_round_num = round_num + 1

        logger.info(f"Ending round {round_num}, looking for next round {next_round_num}")
        logger.info(f"Available rounds: {[r.get('round') for r in tournament.rounds]}")

        for round_config in tournament.rounds:
            config_round = round_config.get("round")
            if config_round is None:
                continue
            config_round_int = int(config_round) if isinstance(config_round, (int, str)) else config_round

            logger.info(f"Checking round config: {config_round} (as int: {config_round_int}) vs next: {next_round_num}")

            if config_round_int == next_round_num:
                next_round = config_round_int
                logger.info(f"Found next round: {next_round}")
                break

        if next_round is None:
            logger.warning(f"No next round found. Current round: {round_num}, Total rounds: {len(tournament.rounds)}")

        # Move to next round or reset if all rounds completed
        if next_round:
            # Automatically start next round
            tournament.current_round = next_round
            tournament.round_status[str(next_round)] = "ongoing"

            # Initialize selected_teams for next round if not exists
            if not tournament.selected_teams:
                tournament.selected_teams = {}
            if str(next_round) not in tournament.selected_teams:
                tournament.selected_teams[str(next_round)] = []

            message = f"Round {round_num} completed. Round {next_round} started automatically."
        else:
            # All rounds completed
            tournament.current_round = 0
            message = f"Round {round_num} completed. All rounds are now complete."

        tournament.save(update_fields=["current_round", "round_status", "selected_teams"])
        cache.delete("tournaments:list:all")

        return Response(
            {
                "message": message,
                "current_round": tournament.current_round,
                "round_status": tournament.round_status,
                "all_rounds_completed": next_round is None,
                "next_round_started": next_round is not None,
            }
        )


class SelectWinnerView(generics.GenericAPIView):
    """
    Select winner for final round (when 2 teams, 1 winner)
    POST /api/tournaments/<tournament_id>/select-winner/
    Body: {"winner_id": 123}
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        logger.debug(
            f"Select winner request - Tournament: {tournament_id}, Winner ID: {request.data.get('winner_id')}, Host: {request.user.id}"  # noqa E501
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        round_num = tournament.current_round
        round_config = next((r for r in tournament.rounds if r["round"] == round_num), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        winner_id = request.data.get("winner_id")
        if not winner_id:
            return Response({"error": "winner_id is required"}, status=400)

        # Get participating teams for current round
        if round_num == 1:
            # For round 1, all confirmed teams are participating
            participating_teams = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).values_list("id", flat=True)
            valid_team_ids = list(participating_teams)
        else:
            # For other rounds, teams selected in previous round are participating
            prev_round_key = str(round_num - 1)
            valid_team_ids = tournament.selected_teams.get(prev_round_key, [])

        # Validate winner is in participating teams
        winner_id_int = int(winner_id)
        if winner_id_int not in valid_team_ids:
            return Response({"error": "Winner must be one of the participating teams for this round"}, status=400)

        # Check if this is a final round (no qualifying_teams or qualifying_teams = 0)
        qualifying_teams = round_config.get("qualifying_teams")
        is_final_round = not qualifying_teams or int(qualifying_teams) == 0

        # Check if it's the last round
        is_last_round = round_num == len(tournament.rounds)

        if not (is_final_round and is_last_round):
            return Response({"error": "Winner selection is only available for final rounds"}, status=400)

        if len(valid_team_ids) < 2:
            return Response({"error": "Final round requires at least 2 teams to select a winner"}, status=400)

        # Save winner
        if not tournament.winners:
            tournament.winners = {}
        round_key = str(round_num)
        tournament.winners[round_key] = winner_id_int

        tournament.save(update_fields=["winners"])
        cache.delete("tournaments:list:all")

        logger.info(f"Winner selected - Tournament: {tournament.id}, Round: {round_num}, Winner ID: {winner_id_int}")

        # Get winner registration details
        winner_registration = TournamentRegistration.objects.get(id=winner_id_int, tournament=tournament)

        # Winner notifications are now sent from EndTournamentView (manage.py) only.
        # Commented out to avoid duplicate notifications when rounds.py and groups.py both fire.
        # try:
        #     registrations = TournamentRegistration.objects.filter(
        #         tournament=tournament, status="confirmed"
        #     ).select_related("team")
        #     winner_team_name = winner_registration.team_name or winner_registration.player.user.username
        #     notifications = []
        #     for reg in registrations:
        #         member_user_ids = TeamMember.objects.filter(
        #             team=reg.team, user__isnull=False
        #         ).values_list("user_id", flat=True)
        #         for user_id in member_user_ids:
        #             notifications.append(
        #                 Notification(
        #                     user_id=user_id,
        #                     type="tournament_result",
        #                     title="Winner Declared",
        #                     message=f"{winner_team_name} has won {tournament.title}!",
        #                     related_id=tournament.id,
        #                     related_type="tournament",
        #                 )
        #             )
        #     if notifications:
        #         Notification.objects.bulk_create(notifications)
        #         logger.info(
        #             f"Winner notifications sent - Tournament: {tournament.id}, Winner: {winner_team_name}, Players notified: {len(notifications)}"
        #         )
        # except Exception as e:
        #     logger.error(f"Failed to send winner notifications: {e}", exc_info=True)

        return Response(
            {
                "message": "Winner selected successfully!",
                "winner": {
                    "id": winner_registration.id,
                    "team_name": winner_registration.team_name or winner_registration.player.user.username,
                    "player_name": winner_registration.player.user.username,
                },
                "round": round_num,
            }
        )
