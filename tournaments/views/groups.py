"""
Group and round management views.
Handles round configuration, group listing, and round results.
"""
import csv
import logging
import random
import re

from django.http import StreamingHttpResponse
from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile, Notification, PlayerProfile, TeamMember
from tournaments.models import Group, RoundScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService
from tournaments.tasks import update_leaderboard
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger("tournaments")


class ConfigureRoundView(generics.GenericAPIView):
    """
    Configure and start a round with groups and matches
    POST /api/tournaments/<tournament_id>/rounds/<round_number>/configure/
    Body: {
        "teams_per_group": 25,
        "qualifying_per_group": 12,
        "matches_per_group": 4
    }
    DELETE — reset a round so it can be reconfigured
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, round_number):
        logger.debug(
            f"Configure round request - Tournament: {tournament_id}, Round: {round_number}, Host: {request.user.id}"
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        logger.info(
            f"Configuring round - Tournament: {tournament.title} ({tournament.id}), Round: {round_number}, Event Mode: {tournament.event_mode}"  # noqa E501
        )

        # Validate round number
        if round_number < 1 or round_number > len(tournament.rounds):
            return Response(
                {"error": f"Invalid round number. Tournament has {len(tournament.rounds)} rounds."}, status=400
            )

        # Scrim-specific logic
        is_scrim = tournament.event_mode == "SCRIM"
        if is_scrim and round_number != 1:
            return Response({"error": "Scrims only support one round."}, status=400)

        # Check if round already configured
        existing_groups = Group.objects.filter(tournament=tournament, round_number=round_number)
        if existing_groups.exists():
            return Response(
                {"error": f"Round {round_number} is already configured with {existing_groups.count()} groups"},
                status=400,
            )

        # Check if this is a 5v5 game (Valorant/COD)
        is_5v5_game = tournament.is_5v5_game()

        # Get configuration from request
        teams_per_group = request.data.get("teams_per_group")
        qualifying_per_group = request.data.get("qualifying_per_group")
        matches_per_group = request.data.get("matches_per_group")

        if is_scrim:
            # Force Scrim parameters
            total_registered = tournament.registrations.filter(status="confirmed").count()
            teams_per_group = total_registered
            qualifying_per_group = 0  # No qualification
            if not matches_per_group:
                matches_per_group = tournament.max_matches
            else:
                matches_per_group = min(int(matches_per_group), 6)
        elif is_5v5_game:
            # 5v5 games (Valorant/COD): only need matches_per_group
            # teams_per_group and qualifying_per_group are fixed at 2 and 1
            if not matches_per_group:
                return Response(
                    {"error": "matches_per_group is required for 5v5 tournaments (1=BO1, 2=BO2, 3=BO3)"},
                    status=400,
                )
            try:
                matches_per_group = int(matches_per_group)
            except (ValueError, TypeError):
                return Response({"error": "matches_per_group must be an integer"}, status=400)

            if matches_per_group < 1:
                return Response(
                    {"error": "matches_per_group must be at least 1"},
                    status=400,
                )
        else:
            if not all([teams_per_group, qualifying_per_group, matches_per_group]):
                return Response(
                    {"error": "Missing required fields: teams_per_group, qualifying_per_group, matches_per_group"},
                    status=400,
                )

        # Type conversion for multi-team games
        if not is_5v5_game:
            try:
                teams_per_group = int(teams_per_group)
                qualifying_per_group = int(qualifying_per_group)
                matches_per_group = int(matches_per_group)
            except (ValueError, TypeError):
                return Response({"error": "All configuration values must be integers"}, status=400)

            # Validate teams_per_group max limit
            if teams_per_group > TournamentGroupService.MAX_TEAMS_PER_GROUP:
                return Response(
                    {"error": f"Teams per group cannot exceed {TournamentGroupService.MAX_TEAMS_PER_GROUP}"}, status=400
                )

        # Get total teams for this round
        if round_number == 1:
            total_teams = tournament.registrations.filter(status="confirmed").count()
        else:
            prev_round_key = str(round_number - 1)
            qualified_team_ids = tournament.selected_teams.get(prev_round_key, [])
            total_teams = len(qualified_team_ids)

        if total_teams == 0:
            return Response({"error": "No teams available for this round"}, status=400)

        # For 5v5 games, check minimum team requirement
        if is_5v5_game and total_teams < 2:
            return Response({"error": "Minimum 2 confirmed teams required for 5v5 tournament"}, status=400)

        # Create groups and matches based on game format
        try:
            if is_5v5_game:
                # 5v5 Head-to-Head Format (Valorant/COD)
                logger.debug(
                    f"Creating 5v5 lobbies - Tournament: {tournament.id}, Round: {round_number}, Total teams: {total_teams}, Matches per lobby: {matches_per_group}"  # noqa E501
                )

                result = TournamentGroupService.create_5v5_groups(
                    tournament=tournament,
                    round_number=round_number,
                    matches_per_group=matches_per_group,
                )

                if 'error' in result:
                    return Response({"error": result['error']}, status=400)

                groups = result['groups']
                bye_team = result['bye_team']
                num_lobbies = result['total_lobbies']
                bye_message = result['bye_message']

                logger.info(
                    f"5v5 Lobbies created successfully - Tournament: {tournament.id}, Round: {round_number}, Lobbies: {num_lobbies}, Bye team: {bye_team.team_name if bye_team else 'None'}"  # noqa E501
                )

            else:
                # Multi-team Format (BGMI, Freefire, Scarfall)
                # Calculate group distribution
                if is_scrim:
                    # Force 1 group for scrims
                    num_groups = 1
                    teams_distribution = [total_teams]
                else:
                    num_groups, teams_distribution = TournamentGroupService.calculate_groups(total_teams, teams_per_group)

                # Validate qualifying teams
                total_qualifying = num_groups * qualifying_per_group
                if not is_scrim and qualifying_per_group > teams_per_group:
                    return Response(
                        {
                            "error": f"Qualifying teams per group ({qualifying_per_group}) cannot exceed teams per group ({teams_per_group})"  # noqa: E501
                        },
                        status=400,
                    )

                logger.debug(
                    f"Creating multi-team groups - Num groups: {num_groups}, Teams per group: {teams_per_group}, Matches per group: {matches_per_group}"  # noqa E501
                )
                groups = TournamentGroupService.create_groups_for_round(
                    tournament=tournament,
                    round_number=round_number,
                    teams_per_group=teams_per_group if not is_scrim else total_teams,
                    qualifying_per_group=qualifying_per_group,
                    matches_per_group=matches_per_group,
                )
                logger.info(
                    f"Multi-team groups created successfully - Tournament: {tournament.id}, Round: {round_number}, Groups: {len(groups)}"  # noqa E501
                )

                bye_team = None
                bye_message = None
                num_lobbies = num_groups

        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            logger.error(
                f"Failed to create groups - Tournament: {tournament.id}, Round: {round_number}, Error: {str(e)}",
                exc_info=True,
            )
            return Response({"error": str(e)}, status=500)

        # Update tournament round status
        if not tournament.round_status:
            tournament.round_status = {}

        is_preconfigure = tournament.status == "upcoming"

        round_key = str(round_number)
        if is_preconfigure:
            # Pre-configure: save groups as draft — do NOT set ongoing or update current_round.
            # This lets the host set up groups/bulk-schedule before the tournament starts,
            # without exposing slot lists or sending notifications to players yet.
            if isinstance(tournament.round_status.get(round_key), dict):
                tournament.round_status[round_key]["status"] = "pre_configured"
            else:
                tournament.round_status[round_key] = {"status": "pre_configured"}
            tournament.save(update_fields=["round_status"])
            logger.info(
                f"Round pre-configured (draft) - Tournament: {tournament.id}, Round: {round_number}"
            )
        else:
            # Tournament already ongoing — set round as active and notify players.
            if isinstance(tournament.round_status.get(round_key), dict):
                tournament.round_status[round_key]["status"] = "ongoing"
            else:
                tournament.round_status[round_key] = {"status": "ongoing"}

            tournament.current_round = round_number
            tournament.save(update_fields=["round_status", "current_round"])

            # Notify all confirmed registered players that groups have been assigned
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
                        f"Group assignment notifications sent - Tournament: {tournament.id}, Round: {round_number}, Players notified: {len(notifications)}"  # noqa E501
                    )
            except Exception as e:
                logger.error(f"Failed to send group assignment notifications: {e}", exc_info=True)

        # Build response
        response_data = {
            "message": f"{'Scrim' if is_scrim else 'Round ' + str(round_number)} configured successfully",
            "num_groups": num_lobbies,
            "groups": [
                {
                    "id": g.id,
                    "group_name": g.group_name,
                    "teams_count": g.teams.count(),
                    "teams": [
                        {
                            "id": team.id,
                            "team_name": team.team_name,
                        }
                        for team in g.teams.all()
                    ] if is_5v5_game else None,
                    "matches_count": g.matches.count(),
                }
                for g in groups
            ],
        }

        if is_5v5_game:
            # 5v5-specific response fields
            response_data["format"] = "5v5_head_to_head"
            response_data["total_lobbies"] = num_lobbies
            response_data["matches_per_lobby"] = matches_per_group
            if bye_team:
                response_data["bye_team"] = {
                    "id": bye_team.id,
                    "team_name": bye_team.team_name,
                }
                response_data["bye_message"] = bye_message
            else:
                response_data["bye_team"] = None
                response_data["bye_message"] = None
        else:
            # Multi-team response fields
            response_data["format"] = "multi_team"
            response_data["teams_distribution"] = teams_distribution if not is_scrim else [total_teams]
            response_data["total_qualifying"] = total_qualifying if not is_scrim else 0

        return Response(response_data)

    def delete(self, request, tournament_id, round_number):
        """
        Reset a round configuration — delete all groups, matches, and scores
        so the organizer can reconfigure from scratch.
        DELETE /api/tournaments/<tournament_id>/rounds/<round_number>/configure/
        """
        logger.info(
            f"Reset round request - Tournament: {tournament_id}, Round: {round_number}, Host: {request.user.id}"
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        # Validate round number
        if round_number < 1 or round_number > len(tournament.rounds):
            return Response(
                {"error": f"Invalid round number. Tournament has {len(tournament.rounds)} rounds."},
                status=400,
            )

        # Check that the round is actually configured
        existing_groups = Group.objects.filter(tournament=tournament, round_number=round_number)
        if not existing_groups.exists():
            return Response(
                {"error": f"Round {round_number} is not configured yet"},
                status=400,
            )

        # Delete groups (cascades to matches and match scores)
        deleted_count = existing_groups.count()
        existing_groups.delete()

        # Delete round scores
        RoundScore.objects.filter(tournament=tournament, round_number=round_number).delete()

        # Reset round status back to upcoming
        round_key = str(round_number)
        if tournament.round_status and round_key in tournament.round_status:
            tournament.round_status[round_key] = {"status": "upcoming"}

        # Reset current_round if it was set to this round
        if tournament.current_round == round_number:
            tournament.current_round = 0

        tournament.save(update_fields=["round_status", "current_round"])

        logger.info(
            f"Round reset successfully - Tournament: {tournament.id}, Round: {round_number}, "
            f"Deleted {deleted_count} groups"
        )

        return Response({
            "message": f"Round {round_number} has been reset. You can now reconfigure it.",
            "deleted_groups": deleted_count,
        })


class ShuffleGroupsView(generics.GenericAPIView):
    """
    Shuffle team assignments across existing groups for a round.
    POST /api/tournaments/<tournament_id>/rounds/<round_number>/shuffle/

    Redistributes all teams randomly across the existing groups while preserving
    the group count and match structure. Only allowed when round_status is 'pre_configured'.
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id, round_number):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        round_key = str(round_number)
        round_status_val = tournament.round_status or {}

        # Support both plain string and dict format for round_status
        status_entry = round_status_val.get(round_key, "upcoming")
        if isinstance(status_entry, dict):
            current_status = status_entry.get("status", "upcoming")
        else:
            current_status = status_entry

        if current_status != "pre_configured":
            return Response(
                {"error": "Groups can only be shuffled when the round is in pre_configured state."},
                status=400,
            )

        groups = list(Group.objects.filter(tournament=tournament, round_number=round_number))
        if not groups:
            return Response({"error": f"Round {round_number} has no configured groups."}, status=400)

        # Collect all teams from all groups in their current distribution sizes
        group_sizes = [group.teams.count() for group in groups]
        all_teams = []
        for group in groups:
            all_teams.extend(list(group.teams.all()))

        if not all_teams:
            return Response({"error": "No teams found in groups."}, status=400)

        # Shuffle all teams randomly
        random.shuffle(all_teams)

        # Redistribute back into the same groups preserving original sizes
        offset = 0
        for group, size in zip(groups, group_sizes):
            new_slice = all_teams[offset: offset + size]
            group.teams.set(new_slice)
            offset += size

        logger.info(
            f"Groups shuffled - Tournament: {tournament.id}, Round: {round_number}, "
            f"Groups: {len(groups)}, Teams: {len(all_teams)}"
        )

        return Response(
            {
                "message": f"Round {round_number} groups have been reshuffled.",
                "groups": len(groups),
                "teams": len(all_teams),
            }
        )


class RoundGroupsListView(generics.GenericAPIView):
    """
    Get all groups for a tournament round
    GET /api/tournaments/<tournament_id>/rounds/<round_number>/groups/
    """

    permission_classes = [IsAuthenticated]  # Allow both hosts and players

    def get(self, request, tournament_id, round_number):
        # Check if user is host or player
        is_host = False
        player_registration = None

        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            is_host = True
        except (HostProfile.DoesNotExist, Tournament.DoesNotExist):
            # If not a host, check if user is a registered player
            try:
                player_profile = PlayerProfile.objects.get(user=request.user)
                tournament = Tournament.objects.get(id=tournament_id)

                # Check if player is registered as captain
                player_registration = TournamentRegistration.objects.filter(
                    tournament=tournament, player=player_profile
                ).first()

                if not player_registration:
                    # Check if player is a team member of any registered team
                    team_ids = TeamMember.objects.filter(user=request.user).values_list("team_id", flat=True)
                    player_registration = TournamentRegistration.objects.filter(
                        tournament=tournament, team_id__in=team_ids
                    ).first()

                if not player_registration:
                    return Response({"error": "You are not registered for this tournament"}, status=403)
            except (PlayerProfile.DoesNotExist, Tournament.DoesNotExist):
                return Response({"error": "Tournament not found or you don't have access"}, status=404)

        # Determine if this round is pre-configured (scheduled before tournament starts).
        # Pre-configured rounds show slot/timing data to players but credentials are stripped
        # until they are explicitly released by the host.
        round_key = str(round_number)
        round_status_val = tournament.round_status.get(round_key) if tournament.round_status else None
        if isinstance(round_status_val, dict):
            round_status_str = round_status_val.get("status", "upcoming")
        else:
            round_status_str = round_status_val or "upcoming"
        is_pre_configured = (round_status_str == "pre_configured")

        # Hosts see all groups; players only see their own group (CRITICAL security rule)
        # Exception: scrims have no group assignment — all registered players see all groups
        # Exception: completed tournaments — all registered players can see all rounds' results
        is_scrim = tournament.event_mode == 'SCRIM'
        is_completed = tournament.status == 'completed'
        if is_host or is_scrim or is_completed:
            groups = Group.objects.filter(tournament=tournament, round_number=round_number)
        else:
            groups = Group.objects.filter(
                tournament=tournament, round_number=round_number, teams=player_registration
            )

        if not groups.exists():
            return Response(
                {"error": f"No groups found for round {round_number}. Configure the round first."}, status=404
            )

        groups_data = []
        for group in groups:
            matches = group.matches.all()
            completed_matches = matches.filter(status="completed").count()

            groups_data.append(
                {
                    "id": group.id,
                    "group_name": group.group_name,
                    "status": group.status,
                    "qualifying_teams": group.qualifying_teams,
                    "teams_count": group.teams.count(),
                    "teams": [
                        {"id": team.id, "team_name": team.team_name, "player_name": team.player.user.username}
                        for team in group.teams.all()
                    ],
                    "matches": [
                        {
                            "id": match.id,
                            "match_number": match.match_number,
                            "status": match.status,
                            # Credentials visible to host always; to players when round is not
                            # pre_configured AND (no scheduled release time OR release time has passed)
                            "match_id": match.match_id if (
                                is_host or (
                                    not is_pre_configured and (
                                        match.credential_release_time is None or
                                        match.credential_release_time <= timezone.now()
                                    )
                                )
                            ) else None,
                            "match_password": match.match_password if (
                                is_host or (
                                    not is_pre_configured and (
                                        match.credential_release_time is None or
                                        match.credential_release_time <= timezone.now()
                                    )
                                )
                            ) else None,
                            "credential_release_time": match.credential_release_time,
                            "scheduled_date": str(match.scheduled_date) if match.scheduled_date else None,
                            "scheduled_time": str(match.scheduled_time) if match.scheduled_time else None,
                            "map_name": match.map_name or None,
                            "started_at": match.started_at,
                            "ended_at": match.ended_at,
                            "scores_submitted": match.scores.exists(),
                            "scores": (
                                [
                                    {
                                        "team_id": score.team.team.id if score.team and score.team.team else None,
                                        "team_name": score.team.team_name,
                                        "profile_picture": score.team.team.profile_picture.url
                                        if score.team and score.team.team and score.team.team.profile_picture
                                        else None,
                                        "position_points": score.position_points,
                                        "kill_points": score.kill_points,
                                        "total_points": score.total_points,
                                        "wins": score.wins,
                                    }
                                    for score in match.scores.all()
                                ]
                                if match.scores.exists()
                                else [
                                    {
                                        "team_id": team.team.id if team.team else None,
                                        "team_name": team.team_name,
                                        "profile_picture": team.team.profile_picture.url
                                        if team.team and team.team.profile_picture
                                        else None,
                                        "position_points": 0,
                                        "kill_points": 0,
                                        "total_points": 0,
                                        "wins": 0,
                                    }
                                    for team in group.teams.all()
                                ]
                            ),
                        }
                        for match in matches
                    ],
                    "matches_per_group": matches.count(),
                    "completed_matches": completed_matches,
                    "total_matches": matches.count(),
                }
            )

        return Response({"round_number": round_number, "groups": groups_data})


class _Echo:
    """Tiny file-like for streaming CSV row by row without buffering."""

    def write(self, value):
        return value


class RoundSlotListExportView(generics.GenericAPIView):
    """
    Export the slot list for a round as a downloadable CSV.

    Returns one row per team with: slot_number, group_name, team_name,
    captain_username, players (comma-joined within the cell). Players see
    the same data they get on the slot list page; hosts see all groups.

    GET /api/tournaments/<tournament_id>/rounds/<round_number>/slots/export/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, tournament_id, round_number):
        # Reuse the same access logic as RoundGroupsListView so we never leak
        # data here that wouldn't show up on the player's slot list page.
        is_host = False
        player_registration = None

        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
            is_host = True
        except (HostProfile.DoesNotExist, Tournament.DoesNotExist):
            try:
                player_profile = PlayerProfile.objects.get(user=request.user)
                tournament = Tournament.objects.get(id=tournament_id)
                player_registration = TournamentRegistration.objects.filter(
                    tournament=tournament, player=player_profile
                ).first()
                if not player_registration:
                    team_ids = TeamMember.objects.filter(user=request.user).values_list(
                        "team_id", flat=True
                    )
                    player_registration = TournamentRegistration.objects.filter(
                        tournament=tournament, team_id__in=team_ids
                    ).first()
                if not player_registration:
                    return Response(
                        {"error": "You are not registered for this tournament"}, status=403
                    )
            except (PlayerProfile.DoesNotExist, Tournament.DoesNotExist):
                return Response(
                    {"error": "Tournament not found or you don't have access"}, status=404
                )

        is_scrim = tournament.event_mode == "SCRIM"
        is_completed = tournament.status == "completed"
        if is_host or is_scrim or is_completed:
            groups = Group.objects.filter(tournament=tournament, round_number=round_number)
        else:
            groups = Group.objects.filter(
                tournament=tournament, round_number=round_number, teams=player_registration
            )

        if not groups.exists():
            return Response({"error": f"No slots found for round {round_number}"}, status=404)

        # Slot numbers restart at 1 per group — each group plays in its own
        # room, so slot 1 of Group A and slot 1 of Group B are different rooms.
        rows = [["slot_number", "group_name", "team_name", "captain_username", "players"]]
        for group in groups.order_by("group_name"):
            slot_counter = 3
            for team_reg in group.teams.all().order_by("id"):
                captain_username = team_reg.player.user.username if team_reg.player else ""
                player_names = []
                team_obj = team_reg.team
                if team_obj:
                    player_names = list(
                        team_obj.members.values_list("username", flat=True)
                    )
                rows.append(
                    [
                        slot_counter,
                        group.group_name,
                        team_reg.team_name or "",
                        captain_username,
                        ", ".join(p for p in player_names if p),
                    ]
                )
                slot_counter += 1

        # Slugify the tournament title so the downloaded filename is friendly
        # (browser will use it via Content-Disposition).
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (tournament.title or "tournament")).strip("-").lower()
        filename = f"{slug or 'tournament'}-round-{round_number}-slots.csv"

        writer = csv.writer(_Echo())

        def stream_rows():
            for row in rows:
                yield writer.writerow(row)

        response = StreamingHttpResponse(stream_rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class RoundResultsView(generics.GenericAPIView):
    """
    Get results and qualified teams for a round
    GET /api/tournaments/<tournament_id>/rounds/<round_number>/results/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, tournament_id, round_number):
        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=404)

        groups = Group.objects.filter(tournament=tournament, round_number=round_number)

        if not groups.exists():
            return Response({"error": f"No groups found for round {round_number}"}, status=404)

        # Check if all groups are completed
        incomplete_groups = groups.filter(status__in=["waiting", "ongoing"])
        if incomplete_groups.exists():
            incomplete_names = [g.group_name for g in incomplete_groups]
            return Response(
                {
                    "error": f"Cannot advance round. The following groups are not completed: {', '.join(incomplete_names)}",  # noqa: E501
                    "incomplete_groups": incomplete_names,
                },
                status=400,
            )

        # Check if this is the final round
        final_round_number = max(r["round"] for r in tournament.rounds)
        is_final_round = round_number == final_round_number

        # Check if this is a 5v5 game
        is_5v5_game = tournament.is_5v5_game()

        results = []
        all_qualified_teams = []

        for group in groups:
            standings = TournamentGroupService.calculate_group_standings(group)

            # Handle 5v5 vs multi-team format
            if is_5v5_game and isinstance(standings, dict) and standings.get('is_5v5'):
                # 5v5 Head-to-Head Format
                group_winner_id = None

                # Determine winner from standings
                if standings['group_winner'] == 'team_a':
                    group_winner_id = standings['team_a']['team_id']
                elif standings['group_winner'] == 'team_b':
                    group_winner_id = standings['team_b']['team_id']

                if is_final_round:
                    qualified = []
                else:
                    # Winner qualifies to next round
                    if group_winner_id:
                        qualified = [standings['team_a'] if standings['group_winner'] == 'team_a' else standings['team_b']]
                        all_qualified_teams.append(group_winner_id)
                    else:
                        qualified = []

                results.append({
                    "group_name": group.group_name,
                    "format": "5v5_head_to_head",
                    "standings": standings,
                    "qualified_teams": qualified,
                    "qualified_count": len(qualified),
                })
            else:
                # Multi-team Format (existing logic)
                qualifying_per_group = group.qualifying_teams

                if is_final_round:
                    qualified = []
                else:
                    qualified = standings[:qualifying_per_group]
                    qualified_team_ids = [t["team_id"] for t in qualified]
                    all_qualified_teams.extend(qualified_team_ids)

                results.append({
                    "group_name": group.group_name,
                    "format": "multi_team",
                    "standings": standings,
                    "qualified_teams": qualified,
                    "qualified_count": len(qualified),
                })

        logger.debug(f"Qualified teams: {all_qualified_teams}")

        if is_final_round:
            # Calculate overall winner from final round
            winner = None

            if is_5v5_game:
                # For 5v5: Winner is the only team that won their final group
                # (should only be 1 group in final round with 2 teams)
                for group in groups:
                    standings = TournamentGroupService.calculate_group_standings(group)
                    if isinstance(standings, dict) and standings.get('is_5v5'):
                        if standings['group_winner'] == 'team_a':
                            winner = {
                                "team_id": standings['team_a']['team_id'],
                                "team_name": standings['team_a']['team_name'],
                                "match_wins": standings['team_a']['match_wins'],
                                "total_points": standings['team_a']['total_points'],
                                "total_kills": standings['team_a']['total_kills'],
                            }
                        elif standings['group_winner'] == 'team_b':
                            winner = {
                                "team_id": standings['team_b']['team_id'],
                                "team_name": standings['team_b']['team_name'],
                                "match_wins": standings['team_b']['match_wins'],
                                "total_points": standings['team_b']['total_points'],
                                "total_kills": standings['team_b']['total_kills'],
                            }
                        break  # Only one final group in 5v5
            else:
                # For multi-team: Aggregate all standings and find top team
                all_final_standings = []
                for group in groups:
                    standings = TournamentGroupService.calculate_group_standings(group)
                    if isinstance(standings, list):
                        all_final_standings.extend(standings)

                # Sort all teams using the same tiebreaking logic as calculate_group_standings
                all_final_standings.sort(
                    key=lambda x: (
                        -x["total_points"],  # Higher points first
                        -x["wins"],  # More wins breaks ties
                        -x["position_points"],  # Better placement breaks ties
                        x["team_name"],  # Alphabetical as final tiebreaker
                    )
                )
                winner = all_final_standings[0] if all_final_standings else None

            # Update tournament winner
            if winner:
                if not tournament.winners:
                    tournament.winners = {}
                tournament.winners[str(round_number)] = winner["team_id"]
                tournament.status = "completed"
                tournament.save(update_fields=["winners", "status"])
                # Trigger leaderboard update when tournament auto-completes via final round
                update_leaderboard.delay()
                # Winner notifications are now sent from EndTournamentView (manage.py) only.
                # Commented out to avoid duplicate notifications when rounds.py and groups.py both fire.
                # try:
                #     registrations = TournamentRegistration.objects.filter(
                #         tournament=tournament, status="confirmed"
                #     ).select_related("team")
                #     winner_team_name = winner.get("team_name", "Unknown Team")
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
                #             f"Winner notifications sent (auto-complete) - Tournament: {tournament.id}, Winner: {winner_team_name}, Players notified: {len(notifications)}"
                #         )
                # except Exception as e:
                #     logger.error(f"Failed to send winner notifications (auto-complete): {e}", exc_info=True)

            return Response(
                {
                    "round_number": round_number,
                    "is_final_round": True,
                    "format": "5v5_head_to_head" if is_5v5_game else "multi_team",
                    "groups": results,
                    "winner": winner,
                    "tournament_completed": True,
                }
            )
        else:
            # Calculate eliminated teams for each group
            total_eliminated = 0

            for i, result in enumerate(results):
                group = groups[i]
                standings = TournamentGroupService.calculate_group_standings(group)

                if is_5v5_game and isinstance(standings, dict) and standings.get('is_5v5'):
                    # 5v5: Loser is eliminated
                    qualified_team_ids = [t['team_id'] for t in result["qualified_teams"]]

                    # Get loser (the team that didn't win)
                    loser = None
                    if standings['group_winner'] == 'team_a':
                        loser = {
                            "team_id": standings['team_b']['team_id'],
                            "team_name": standings['team_b']['team_name'],
                            "match_wins": standings['team_b']['match_wins'],
                            "total_points": standings['team_b']['total_points'],
                            "total_kills": standings['team_b']['total_kills'],
                            "rank": 2,
                        }
                    elif standings['group_winner'] == 'team_b':
                        loser = {
                            "team_id": standings['team_a']['team_id'],
                            "team_name": standings['team_a']['team_name'],
                            "match_wins": standings['team_a']['match_wins'],
                            "total_points": standings['team_a']['total_points'],
                            "total_kills": standings['team_a']['total_kills'],
                            "rank": 2,
                        }

                    eliminated_teams = [loser] if loser else []
                    result["eliminated_teams"] = eliminated_teams
                    result["eliminated_count"] = len(eliminated_teams)
                    total_eliminated += len(eliminated_teams)
                else:
                    # Multi-team: Teams not in qualifying list are eliminated
                    qualified_team_ids = [t["team_id"] for t in result["qualified_teams"]]

                    # Add rank to standings
                    for rank, standing in enumerate(standings, start=1):
                        standing["rank"] = rank

                    # Get eliminated teams (those not in qualifying list)
                    eliminated_teams = [
                        {
                            "team_id": s["team_id"],
                            "team_name": s["team_name"],
                            "total_points": s["total_points"],
                            "position_points": s.get("position_points", 0),
                            "kill_points": s.get("kill_points", 0),
                            "wins": s["wins"],
                            "rank": s["rank"],
                        }
                        for s in standings
                        if s["team_id"] not in qualified_team_ids
                    ]

                    result["eliminated_teams"] = eliminated_teams
                    result["eliminated_count"] = len(eliminated_teams)
                    total_eliminated += len(eliminated_teams)

            # Update tournament selected_teams for this round
            # IMPORTANT: Deduplicate qualified teams to handle cases where the same team
            # appears in multiple groups in the current round (e.g., 8 lobbies with 4 teams)
            unique_qualified_teams = list(dict.fromkeys(all_qualified_teams))  # Preserves order, removes duplicates

            if not tournament.selected_teams:
                tournament.selected_teams = {}

            # Include bye team in selected_teams if it exists for this round
            round_key = str(round_number)
            bye_team_id = None
            if tournament.round_status and isinstance(tournament.round_status.get(round_key), dict):
                bye_team_id = tournament.round_status[round_key].get("bye_team_id")

            teams_for_next_round = unique_qualified_teams.copy()
            if bye_team_id:
                teams_for_next_round.append(bye_team_id)  # Add bye team to next round

            tournament.selected_teams[str(round_number)] = teams_for_next_round

            # Mark round as completed while preserving bye_team_id in round_status
            if not tournament.round_status:
                tournament.round_status = {}
            if isinstance(tournament.round_status.get(round_key), dict):
                tournament.round_status[round_key]["status"] = "completed"
            else:
                tournament.round_status[round_key] = {"status": "completed"}

            tournament.save(update_fields=["selected_teams", "round_status"])

            return Response(
                {
                    "round_number": round_number,
                    "current_round": round_number,
                    "is_final_round": False,
                    "format": "5v5_head_to_head" if is_5v5_game else "multi_team",
                    "groups": results,
                    "total_qualified": len(all_qualified_teams),
                    "total_eliminated": total_eliminated,
                    "next_round": round_number + 1,
                }
            )
