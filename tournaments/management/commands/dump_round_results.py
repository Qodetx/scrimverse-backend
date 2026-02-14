from django.core.management.base import BaseCommand
from django.utils import timezone
import json

from tournaments.models import Tournament, Group, Match, MatchScore


class Command(BaseCommand):
    help = "Dump tournament round results as JSON"

    def add_arguments(self, parser):
        parser.add_argument("--tournament", type=int, required=True, help="Tournament ID")
        parser.add_argument("--round", type=int, required=True, help="Round number")

    def handle(self, *args, **options):
        tournament_id = options["tournament"]
        round_number = options["round"]

        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tournament {tournament_id} not found"))
            return

        groups_qs = Group.objects.filter(tournament=tournament, round_number=round_number).order_by("id")
        result = {
            "round_number": round_number,
            "current_round": tournament.current_round,
            "is_final_round": tournament.is_final_round if hasattr(tournament, "is_final_round") else False,
            "format": getattr(tournament, "format", "5v5_head_to_head"),
            "groups": [],
            "total_qualified": 0,
            "total_eliminated": 0,
            "next_round": round_number + 1,
        }

        total_qualified = 0
        total_eliminated = 0

        for group in groups_qs:
            teams = list(group.teams.all())
            # Prepare team stats mapping
            team_stats = {team.id: {"team_id": team.id, "team_name": getattr(team, "team_name", str(team)), "match_wins": 0, "total_points": 0, "total_kills": 0} for team in teams}

            match_results = []
            for match in group.matches.all().order_by("match_number"):
                scores = list(MatchScore.objects.filter(match=match).order_by("id"))
                # Map scores by team id
                score_map = {s.team.id: s for s in scores}

                if len(teams) >= 2:
                    a = teams[0]
                    b = teams[1]
                    sa = score_map.get(a.id)
                    sb = score_map.get(b.id)

                    team_a_points = (sa.position_points + sa.kill_points) if sa else 0
                    team_b_points = (sb.position_points + sb.kill_points) if sb else 0
                    team_a_kills = sa.kill_points if sa else 0
                    team_b_kills = sb.kill_points if sb else 0
                    winner = None
                    if sa and sb:
                        if sa.wins > sb.wins:
                            winner = "team_a"
                        elif sb.wins > sa.wins:
                            winner = "team_b"
                        else:
                            winner = "draw"

                    match_results.append({
                        "match_number": match.match_number,
                        "team_a_points": team_a_points,
                        "team_b_points": team_b_points,
                        "team_a_kills": team_a_kills,
                        "team_b_kills": team_b_kills,
                        "winner": winner,
                        "status": match.status,
                    })

                    # Aggregate
                    if sa:
                        team_stats[a.id]["match_wins"] += sa.wins
                        team_stats[a.id]["total_points"] += (sa.position_points + sa.kill_points)
                        team_stats[a.id]["total_kills"] += sa.kill_points
                    if sb:
                        team_stats[b.id]["match_wins"] += sb.wins
                        team_stats[b.id]["total_points"] += (sb.position_points + sb.kill_points)
                        team_stats[b.id]["total_kills"] += sb.kill_points

            # Determine series score and winner for 2-team groups
            qualified = []
            eliminated = []
            if len(teams) == 2:
                a = teams[0]
                b = teams[1]
                a_stats = team_stats[a.id]
                b_stats = team_stats[b.id]

                series_score = {"team_a_wins": a_stats["match_wins"], "team_b_wins": b_stats["match_wins"]}
                if a_stats["match_wins"] > b_stats["match_wins"]:
                    group_winner = "team_a"
                    qualified.append(a_stats)
                    eliminated.append({**b_stats, "rank": 2})
                elif b_stats["match_wins"] > a_stats["match_wins"]:
                    group_winner = "team_b"
                    qualified.append(b_stats)
                    eliminated.append({**a_stats, "rank": 2})
                else:
                    group_winner = None

                total_qualified += len(qualified)
                total_eliminated += len(eliminated)

                standings = {
                    "is_5v5": getattr(tournament, "is_5v5_game", lambda: True)(),
                    "team_a": a_stats,
                    "team_b": b_stats,
                    "match_results": match_results,
                    "series_score": series_score,
                    "group_winner": group_winner,
                }

                group_obj = {
                    "group_name": getattr(group, "group_name", str(group)),
                    "format": getattr(group, "format", "5v5_head_to_head"),
                    "standings": standings,
                    "qualified_teams": qualified,
                    "qualified_count": len(qualified),
                    "eliminated_teams": eliminated,
                    "eliminated_count": len(eliminated),
                }
            else:
                # Non 2-team groups: minimal info
                group_obj = {"group_name": getattr(group, "group_name", str(group)), "info": "non head-to-head group"}

            result["groups"].append(group_obj)

        result["total_qualified"] = total_qualified
        result["total_eliminated"] = total_eliminated

        self.stdout.write(json.dumps(result, indent=2))
