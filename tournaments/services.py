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
        # Check if this is a 5v5 head-to-head group (exactly 2 teams)
        teams_count = group.teams.count()
        
        if teams_count == 2:
            # 5v5 Head-to-Head Format
            return TournamentGroupService._calculate_5v5_standings(group)
        else:
            # Multi-team format (existing logic)
            return TournamentGroupService._calculate_multi_team_standings(group)

    @staticmethod
    def _calculate_multi_team_standings(group: Group) -> List[dict]:
        """
        Calculate standings for multi-team groups (BGMI, Freefire, Scarfall)
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

        # Sort by multiple criteria for consistent tiebreaking:
        # 1. Total points (descending)
        # 2. Wins (descending)
        # 3. Kill points (descending)
        # 4. Team name (ascending, for final tiebreaker)
        standings.sort(
            key=lambda x: (
                -x["total_points"],  # Higher points first
                -x["wins"],  # More wins breaks ties
                -x["kill_points"],  # More kills breaks ties
                x["team_name"],  # Alphabetical as final tiebreaker
            )
        )

        return standings

    @staticmethod
    def _calculate_5v5_standings(group: Group) -> dict:
        """
        Calculate standings for 5v5 head-to-head groups (Valorant, COD)
        Returns head-to-head format with match results and series score
        """
        teams = list(group.teams.all())
        if len(teams) != 2:
            return {}
        
        team_a = teams[0]
        team_b = teams[1]
        
        # Get all matches in this group
        matches = Match.objects.filter(group=group).order_by('match_number')
        
        match_results = []
        team_a_wins = 0
        team_b_wins = 0
        team_a_total_pts = 0
        team_b_total_pts = 0
        team_a_total_kills = 0
        team_b_total_kills = 0
        
        for match in matches:
            # Get scores for both teams
            team_a_score = MatchScore.objects.filter(match=match, team=team_a).first()
            team_b_score = MatchScore.objects.filter(match=match, team=team_b).first()
            
            team_a_pts = team_a_score.total_points if team_a_score else 0
            team_b_pts = team_b_score.total_points if team_b_score else 0
            team_a_kills = team_a_score.kill_points if team_a_score else 0
            team_b_kills = team_b_score.kill_points if team_b_score else 0
            
            # Determine match winner
            winner = None
            if match.winner:
                winner = 'team_a' if match.winner.id == team_a.id else 'team_b'
                if winner == 'team_a':
                    team_a_wins += 1
                else:
                    team_b_wins += 1
            
            match_results.append({
                'match_number': match.match_number,
                'team_a_points': team_a_pts,
                'team_b_points': team_b_pts,
                'team_a_kills': team_a_kills,
                'team_b_kills': team_b_kills,
                'winner': winner,
                'status': match.status
            })
            
            # Aggregate totals
            team_a_total_pts += team_a_pts
            team_b_total_pts += team_b_pts
            team_a_total_kills += team_a_kills
            team_b_total_kills += team_b_kills
        
        # Determine group winner
        group_winner = None
        if group.winner:
            group_winner = 'team_a' if group.winner.id == team_a.id else 'team_b'
        
        return {
            'is_5v5': True,
            'team_a': {
                'team_id': team_a.id,
                'team_name': team_a.team_name,
                'match_wins': team_a_wins,
                'total_points': team_a_total_pts,
                'total_kills': team_a_total_kills,
            },
            'team_b': {
                'team_id': team_b.id,
                'team_name': team_b.team_name,
                'match_wins': team_b_wins,
                'total_points': team_b_total_pts,
                'total_kills': team_b_total_kills,
            },
            'match_results': match_results,
            'series_score': {
                'team_a_wins': team_a_wins,
                'team_b_wins': team_b_wins
            },
            'group_winner': group_winner
        }

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

    @staticmethod
    def create_5v5_groups(
        tournament: Tournament,
        round_number: int,
        matches_per_group: int,
    ) -> dict:
        """
        Create 5v5 head-to-head groups (lobbies) for Valorant/COD tournaments
        Each group contains exactly 2 teams

        Args:
            tournament: Tournament instance
            round_number: Round number (1, 2, 3, etc.)
            matches_per_group: Number of matches per lobby (1=BO1, 2=BO2, 3=BO3)

        Returns:
            Dict with:
                - groups: List of created Group instances
                - bye_team: TournamentRegistration if odd teams, else None
                - total_lobbies: Number of lobbies created
                - bye_message: Message about bye team if applicable
        """
        # Validation
        if not tournament.is_5v5_game():
            return {'error': 'Tournament is not a 5v5 game'}
        
        if matches_per_group not in [1, 2, 3, 4]:
            return {'error': 'matches_per_group must be 1, 2, 3, or 4'}
        
        # Get confirmed teams for this round
        teams = TournamentGroupService._get_confirmed_teams(tournament, round_number)
        
        if len(teams) == 0:
            return {'error': 'No confirmed teams to create groups'}
        
        if len(teams) == 1:
            return {'error': 'Minimum 2 confirmed teams required for 5v5 tournament'}
        
        # Handle odd number of teams (bye logic)
        even_teams, bye_team = TournamentGroupService._assign_bye_team(teams)
        
        # Shuffle teams for random matchmaking
        random.shuffle(even_teams)
        
        # Create groups (lobbies) with exactly 2 teams each
        groups = []
        num_lobbies = len(even_teams) // 2
        
        for lobby_num in range(num_lobbies):
            # Get 2 teams for this lobby
            team_a = even_teams[lobby_num * 2]
            team_b = even_teams[lobby_num * 2 + 1]
            
            # Create group with "Lobby X" naming
            lobby_name = f"Lobby {lobby_num + 1}"
            group = Group.objects.create(
                tournament=tournament,
                round_number=round_number,
                group_name=lobby_name,
                qualifying_teams=1,  # Only 1 team qualifies (the winner)
                status="waiting"
            )
            
            # Assign both teams to this group
            group.teams.set([team_a, team_b])
            
            # Create matches for this group based on matches_per_group
            TournamentGroupService.create_matches_for_group(group, matches_per_group)
            
            groups.append(group)
        
        # Prepare return data
        result = {
            'groups': groups,
            'bye_team': bye_team,
            'total_lobbies': num_lobbies,
        }
        
        if bye_team:
            result['bye_message'] = f"{bye_team.team_name} has a bye (automatic advance to next round)"
            # Store bye team in tournament metadata for tracking
            if not tournament.round_status:
                tournament.round_status = {}
            round_key = str(round_number)
            if round_key not in tournament.round_status:
                tournament.round_status[round_key] = {}
            tournament.round_status[round_key]['bye_team_id'] = bye_team.id
            tournament.save(update_fields=['round_status'])
        else:
            result['bye_message'] = None
        
        return result

    @staticmethod
    def _get_confirmed_teams(tournament: Tournament, round_number: int) -> List[TournamentRegistration]:
        """
        Get confirmed teams for a specific round
        
        Args:
            tournament: Tournament instance
            round_number: Round number
            
        Returns:
            List of TournamentRegistration instances
        """
        if round_number == 1:
            # First round: use all registered and confirmed teams
            teams = list(tournament.registrations.filter(status="confirmed"))
        else:
            # Subsequent rounds: use qualified teams from previous round
            prev_round_key = str(round_number - 1)
            qualified_team_ids = tournament.selected_teams.get(prev_round_key, [])
            teams = list(TournamentRegistration.objects.filter(id__in=qualified_team_ids))
        
        return teams

    @staticmethod
    def _assign_bye_team(teams: List[TournamentRegistration]) -> Tuple[List[TournamentRegistration], TournamentRegistration]:
        """
        Handle odd number of teams by assigning a bye to one random team
        
        Args:
            teams: List of TournamentRegistration instances
            
        Returns:
            Tuple of (even_teams_list, bye_team or None)
        """
        if len(teams) % 2 == 1:
            # Odd number: select random team for bye
            bye_team = random.choice(teams)
            even_teams = [t for t in teams if t.id != bye_team.id]
            return (even_teams, bye_team)
        else:
            # Even number: no bye needed
            return (teams, None)
