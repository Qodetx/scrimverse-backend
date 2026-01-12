"""
Service layer for Tournament Groups and Matches system
Handles complex business logic for group division, team distribution, and scoring
"""
import random
from typing import List, Tuple

from django.db.models import Sum

from tournaments.models import Group, Match, MatchScore, RoundScore, Tournament, TournamentRegistration


class TournamentGroupService:
    """Service class for managing tournament groups and matches"""

    MAX_TEAMS_PER_GROUP = 25

    @staticmethod
    def calculate_groups(total_teams: int, teams_per_group: int) -> Tuple[int, List[int]]:
        """
        Calculate number of groups and distribution of teams
        """
        if teams_per_group > TournamentGroupService.MAX_TEAMS_PER_GROUP:
            raise ValueError(f"Teams per group cannot exceed {TournamentGroupService.MAX_TEAMS_PER_GROUP}")

        if teams_per_group <= 0:
            raise ValueError("Teams per group must be greater than 0")

        # Determine number of groups by rounding total / target
        num_groups = round(total_teams / teams_per_group)
        if num_groups == 0:
            num_groups = 1

        # Calculate base number of teams per group and remainder
        base_per_group = total_teams // num_groups
        remainder = total_teams % num_groups

        # Distribute teams as evenly as possible
        teams_distribution = []
        for i in range(num_groups):
            count = base_per_group
            if i < remainder:
                count += 1
            teams_distribution.append(count)

        # Safety check for max limit (in case rounding leads to overflow)
        if max(teams_distribution) > TournamentGroupService.MAX_TEAMS_PER_GROUP:
            # If overflow, we MUST add at least one more group
            new_num_groups = num_groups + 1
            return TournamentGroupService.calculate_groups(total_teams, total_teams // new_num_groups + 1)

        return num_groups, teams_distribution

    @staticmethod
    def create_groups_for_round(
        tournament: Tournament,
        round_number: int,
        teams_per_group: int,
        qualifying_per_group: int,
        matches_per_group: int,
    ) -> List[Group]:
        """
        Create groups for a tournament round

        Args:
            tournament: Tournament instance
            round_number: Round number (1, 2, 3, etc.)
            teams_per_group: Maximum teams per group
            qualifying_per_group: Number of teams that qualify from each group
            matches_per_group: Number of matches to play in each group

        Returns:
            List of created Group instances
        """
        # Get teams for this round
        if round_number == 1:
            # First round: use all registered and confirmed teams
            teams = list(tournament.registrations.filter(status="confirmed"))
        else:
            # Subsequent rounds: use qualified teams from previous round
            prev_round_key = str(round_number - 1)
            qualified_team_ids = tournament.selected_teams.get(prev_round_key, [])
            teams = list(TournamentRegistration.objects.filter(id__in=qualified_team_ids))

        total_teams = len(teams)

        if total_teams == 0:
            raise ValueError("No teams available for this round")

        # Calculate group distribution
        num_groups, teams_distribution = TournamentGroupService.calculate_groups(total_teams, teams_per_group)

        # Shuffle teams for random distribution
        random.shuffle(teams)

        # Create groups
        groups = []
        team_index = 0
        group_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        for group_num in range(num_groups):
            group_name = f"Group {group_letters[group_num]}"
            group = Group.objects.create(
                tournament=tournament,
                round_number=round_number,
                group_name=group_name,
                qualifying_teams=qualifying_per_group,
            )

            # Assign teams to this group
            num_teams_in_group = teams_distribution[group_num]
            group_teams = teams[team_index : team_index + num_teams_in_group]
            group.teams.set(group_teams)

            # Create matches for this group
            TournamentGroupService.create_matches_for_group(group, matches_per_group)

            groups.append(group)
            team_index += num_teams_in_group

        return groups

    @staticmethod
    def create_matches_for_group(group: Group, num_matches: int) -> List[Match]:
        """
        Create match instances for a group

        Args:
            group: Group instance
            num_matches: Number of matches to create

        Returns:
            List of created Match instances
        """
        matches = []
        for match_num in range(1, num_matches + 1):
            match = Match.objects.create(group=group, match_number=match_num, status="waiting")
            matches.append(match)

        return matches

    @staticmethod
    def calculate_group_standings(group: Group) -> List[dict]:
        """
        Calculate team standings within a group based on aggregate match scores

        Args:
            group: Group instance

        Returns:
            List of dicts with team standings, sorted by total points descending
            Format: [{'team': TournamentRegistration, 'total_points': int, ...}, ...]
        """
        standings = []

        for team in group.teams.all():
            # Aggregate scores from all matches in this group
            match_scores = MatchScore.objects.filter(match__group=group, team=team).aggregate(
                total_pp=Sum("position_points"), total_kp=Sum("kill_points"), total_wins=Sum("wins")
            )

            total_points = (match_scores["total_pp"] or 0) + (match_scores["total_kp"] or 0)

            standings.append(
                {
                    "team_id": team.id,
                    "team_name": team.team_name,
                    "position_points": match_scores["total_pp"] or 0,
                    "kill_points": match_scores["total_kp"] or 0,
                    "wins": match_scores["total_wins"] or 0,
                    "total_points": total_points,
                }
            )

        # Sort by total points descending
        standings.sort(key=lambda x: x["total_points"], reverse=True)

        return standings

    @staticmethod
    def select_qualifying_teams(group: Group, qualifying_per_group: int) -> List[int]:
        """
        Select top N teams from a group to advance to next round

        Args:
            group: Group instance
            qualifying_per_group: Number of teams to qualify

        Returns:
            List of team IDs (TournamentRegistration IDs)
        """
        standings = TournamentGroupService.calculate_group_standings(group)
        qualified_teams = standings[:qualifying_per_group]
        return [team["team_id"] for team in qualified_teams]

    @staticmethod
    def calculate_round_scores(tournament: Tournament, round_number: int):
        """
        Calculate and update RoundScore for all teams in a round
        Aggregates scores from all matches in all groups of this round

        Args:
            tournament: Tournament instance
            round_number: Round number
        """
        groups = Group.objects.filter(tournament=tournament, round_number=round_number)

        for group in groups:
            for team in group.teams.all():
                # Get or create RoundScore
                round_score, created = RoundScore.objects.get_or_create(
                    tournament=tournament, round_number=round_number, team=team
                )

                # Calculate from matches
                round_score.calculate_from_matches()

    @staticmethod
    def calculate_tournament_winner(tournament: Tournament) -> TournamentRegistration:
        """
        Calculate tournament winner based on final round scores
        Winner = team with highest points in the final round (NOT cumulative)

        Args:
            tournament: Tournament instance

        Returns:
            TournamentRegistration instance of the winner
        """
        if not tournament.rounds:
            raise ValueError("Tournament has no rounds configured")

        # Get final round number
        final_round = max(r["round"] for r in tournament.rounds)

        # Get scores from final round, ordered by total points
        final_scores = RoundScore.objects.filter(tournament=tournament, round_number=final_round).order_by(
            "-total_points"
        )

        if not final_scores.exists():
            raise ValueError("No scores found for final round")

        winner = final_scores.first().team
        return winner
