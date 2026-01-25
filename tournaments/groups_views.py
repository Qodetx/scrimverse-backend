"""
API views for Groups and Matches system
Handles round configuration, group management, and match operations
"""
import logging

from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile, PlayerProfile, TeamMember
from tournaments.models import Group, Match, MatchScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService

logger = logging.getLogger("tournaments")


class IsHostUser(permissions.BasePermission):
    """Permission class for Host users"""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "host"


class ConfigureRoundView(generics.GenericAPIView):
    """
    Configure and start a round with groups and matches
    POST /api/tournaments/<tournament_id>/rounds/<round_number>/configure/
    Body: {
        "teams_per_group": 25,
        "qualifying_per_group": 12,
        "matches_per_group": 4
    }
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
        else:
            if not all([teams_per_group, qualifying_per_group, matches_per_group]):
                return Response(
                    {"error": "Missing required fields: teams_per_group, qualifying_per_group, matches_per_group"},
                    status=400,
                )

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

        # Calculate group distribution
        try:
            if is_scrim:
                # Force 1 group for scrims
                num_groups = 1
                teams_distribution = [total_teams]
            else:
                num_groups, teams_distribution = TournamentGroupService.calculate_groups(total_teams, teams_per_group)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        # Validate qualifying teams
        total_qualifying = num_groups * qualifying_per_group
        if not is_scrim and qualifying_per_group > teams_per_group:
            return Response(
                {
                    "error": f"Qualifying teams per group ({qualifying_per_group}) cannot exceed teams per group ({teams_per_group})"  # noqa: E501
                },
                status=400,
            )

        # Create groups and matches
        try:
            logger.debug(
                f"Creating groups - Num groups: {num_groups}, Teams per group: {teams_per_group}, Matches per group: {matches_per_group}"  # noqa E501
            )
            groups = TournamentGroupService.create_groups_for_round(
                tournament=tournament,
                round_number=round_number,
                teams_per_group=teams_per_group if not is_scrim else total_teams,
                qualifying_per_group=qualifying_per_group,
                matches_per_group=matches_per_group,
            )
            logger.info(
                f"Groups created successfully - Tournament: {tournament.id}, Round: {round_number}, Groups: {len(groups)}"  # noqa E501
            )
        except Exception as e:
            logger.error(
                f"Failed to create groups - Tournament: {tournament.id}, Round: {round_number}, Error: {str(e)}",
                exc_info=True,
            )
            return Response({"error": str(e)}, status=500)

        # Update tournament round status
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status[str(round_number)] = "ongoing"
        tournament.current_round = round_number
        tournament.save(update_fields=["round_status", "current_round"])

        return Response(
            {
                "message": f"{'Scrim' if is_scrim else 'Round ' + str(round_number)} configured successfully ({num_groups} group created)",  # noqa: E501
                "num_groups": num_groups,
                "teams_distribution": teams_distribution,
                "total_qualifying": total_qualifying,
                "groups": [
                    {
                        "id": g.id,
                        "group_name": g.group_name,
                        "teams_count": g.teams.count(),
                        "matches_count": g.matches.count(),
                    }
                    for g in groups
                ],
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
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        except (HostProfile.DoesNotExist, Tournament.DoesNotExist):
            # If not a host, check if user is a registered player
            try:
                player_profile = PlayerProfile.objects.get(user=request.user)
                tournament = Tournament.objects.get(id=tournament_id)

                # Check if player is registered as captain OR is a member of a registered team
                is_captain = TournamentRegistration.objects.filter(
                    tournament=tournament, player=player_profile
                ).exists()

                # Check if player is a team member of any registered team
                team_ids = TeamMember.objects.filter(user=request.user).values_list("team_id", flat=True)
                is_team_member = TournamentRegistration.objects.filter(
                    tournament=tournament, team_id__in=team_ids
                ).exists()

                if not (is_captain or is_team_member):
                    return Response({"error": "You are not registered for this tournament"}, status=403)
            except (PlayerProfile.DoesNotExist, Tournament.DoesNotExist):
                return Response({"error": "Tournament not found or you don't have access"}, status=404)

        groups = Group.objects.filter(tournament=tournament, round_number=round_number)

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
                            "match_id": match.match_id,
                            "match_password": match.match_password,
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

        try:
            match = Match.objects.get(group=group, match_number=match_number)
        except Match.DoesNotExist:
            return Response({"error": f"Match {match_number} not found in {group.group_name}"}, status=404)

        if match.status == "completed":
            return Response({"error": "Match is already completed"}, status=400)

        # Enforce sequential match flow: can only start match N if match N-1 is completed with scores
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

                # Check if previous match has scores submitted
                if not previous_match.scores.exists():
                    return Response(
                        {
                            "error": f"Cannot start Match {match_number}. Scores must be submitted for Match {match_number - 1} first."  # noqa: E501
                        },
                        status=400,
                    )

        # Update match details
        match.match_id = match_id
        match.match_password = match_password
        match.status = "ongoing"
        match.started_at = timezone.now()
        match.save()

        # Update group status to ongoing if it was waiting
        if group.status == "waiting":
            group.status = "ongoing"
            group.save(update_fields=["status"])

        return Response(
            {
                "message": f"Match {match_number} started successfully",
                "match": {
                    "id": match.id,
                    "match_number": match.match_number,
                    "match_id": match.match_id,
                    "match_password": match.match_password,
                    "status": match.status,
                    "started_at": match.started_at,
                },
            }
        )
        logger.debug(
            f"Match {match_number} started successfully - Tournament: {tournament.title} ({tournament.id}), Group: {group.id}, Match: {match.id}"  # noqa E501
        )


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
        logger.debug(
            f"Match {match.match_number} ended successfully - Tournament: {tournament.title} ({tournament.id}), Match: {match.id}"  # noqa E501
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

        # Update RoundScore aggregates
        logger.debug(f"Calculating round scores - Tournament: {tournament.id}, Round: {match.group.round_number}")
        TournamentGroupService.calculate_round_scores(tournament, match.group.round_number)

        # Check if all matches in the group are completed with scores
        group = match.group
        logger.info(
            f"Match scores submitted - Match: {match_id}, Scores: {created_count}, Group: {group.group_name}"
        )  # noqa E501
        all_matches_scored = all(m.scores.exists() for m in group.matches.filter(status="completed"))

        if all_matches_scored and group.matches.filter(status="completed").count() == group.matches.count():
            group.status = "completed"
            group.save(update_fields=["status"])

        return Response(
            {
                "message": f"Scores submitted successfully for {created_count} teams",
                "match_id": match.id,
                "match_number": match.match_number,
                "group_completed": group.status == "completed",
            }
        )


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

        results = []
        all_qualified_teams = []

        for group in groups:
            standings = TournamentGroupService.calculate_group_standings(group)

            # Use the qualifying_teams stored in the group
            qualifying_per_group = group.qualifying_teams

            if is_final_round:
                # In final round, we don't qualify teams, we select a winner
                # Winner is the top team across all groups in the final round
                qualified = []
                qualified_team_ids = []
            else:
                qualified = standings[:qualifying_per_group]
                qualified_team_ids = [t["team_id"] for t in qualified]
                all_qualified_teams.extend(qualified_team_ids)

            results.append(
                {
                    "group_name": group.group_name,
                    "standings": standings,
                    "qualified_teams": qualified,
                    "qualified_count": len(qualified),
                }
            )
        logger.debug(f"Qualified teams: {all_qualified_teams}")

        if is_final_round:
            # Calculate overall winner from final round
            all_final_standings = []
            for group in groups:
                standings = TournamentGroupService.calculate_group_standings(group)
                all_final_standings.extend(standings)

            # Sort all teams using the same tiebreaking logic as calculate_group_standings
            # This ensures consistent rankings even when all teams have 0 points
            all_final_standings.sort(
                key=lambda x: (
                    -x["total_points"],  # Higher points first
                    -x["wins"],  # More wins breaks ties
                    -x["kill_points"],  # More kills breaks ties
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

            return Response(
                {
                    "round_number": round_number,
                    "is_final_round": True,
                    "groups": results,
                    "results": all_final_standings,  # Return full sorted standings
                    "winner": winner,
                    "tournament_completed": True,
                }
            )
            logger.debug(f"Final round completed - results: {all_final_standings}")
        else:
            # Calculate eliminated teams for each group
            total_eliminated = 0
            for i, result in enumerate(results):
                group = groups[i]
                standings = TournamentGroupService.calculate_group_standings(group)
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
            if not tournament.selected_teams:
                tournament.selected_teams = {}
            tournament.selected_teams[str(round_number)] = all_qualified_teams

            # Mark round as completed
            if not tournament.round_status:
                tournament.round_status = {}
            tournament.round_status[str(round_number)] = "completed"

            tournament.save(update_fields=["selected_teams", "round_status"])

            return Response(
                {
                    "round_number": round_number,
                    "current_round": round_number,
                    "is_final_round": False,
                    "groups": results,
                    "total_qualified": len(all_qualified_teams),
                    "total_eliminated": total_eliminated,
                    "next_round": round_number + 1,
                }
            )
            logger.debug(
                f"Round {round_number} completed - total qualified: {len(all_qualified_teams)}, total eliminated: {total_eliminated}, moving to next round {round_number + 1}"  # noqa E501
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
            from accounts.models import User

            # Enrich with player profile data from team_members JSON
            for member in team_members:
                # Try to get player by ID first, then by username
                player_id = member.get("id")
                username = member.get("username")

                player_profile = None

                if player_id:
                    try:
                        player_profile = PlayerProfile.objects.select_related("user").get(id=player_id)
                    except PlayerProfile.DoesNotExist:
                        pass

                if not player_profile and username:
                    try:
                        user = User.objects.get(username=username, user_type="player")
                        player_profile = user.player_profile
                    except (User.DoesNotExist, PlayerProfile.DoesNotExist, AttributeError):
                        pass

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

        # If no players from team_members, try to get from Team model
        elif registration.team:
            from accounts.models import TeamMember

            # Get all team members from the Team
            team_members_qs = TeamMember.objects.filter(team=registration.team).select_related(
                "user", "user__player_profile"
            )

            for team_member in team_members_qs:
                try:
                    player_profile = team_member.user.player_profile
                    players_data.append(
                        {
                            "id": player_profile.id,
                            "username": team_member.user.username,
                            "preferred_games": player_profile.preferred_games,
                            "bio": player_profile.bio,
                            "profile_picture": (
                                player_profile.user.profile_picture.url if player_profile.user.profile_picture else None
                            ),
                            "is_captain": team_member.is_captain,
                        }
                    )
                except (PlayerProfile.DoesNotExist, AttributeError):
                    logger.warning(
                        f"Player profile not found for team member - Team ID: {registration.team_id}, User ID: {team_member.user_id}"  # noqa E501
                    )
                    continue

        return Response(
            {
                "tournament_id": tournament.id,
                "registration_id": registration.id,
                "team_name": registration.team_name,
                "players": players_data,
                "total_players": len(players_data),
            }
        )
