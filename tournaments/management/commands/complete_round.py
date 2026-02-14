from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tournaments.models import Tournament, Group, Match, MatchScore
from tournaments.services import TournamentGroupService


class Command(BaseCommand):
    help = "Automatically complete all matches for a tournament round with deterministic scores"

    def add_arguments(self, parser):
        parser.add_argument("--tournament", type=int, required=True, help="Tournament ID")
        parser.add_argument("--round", type=int, required=True, help="Round number to complete")

    def handle(self, *args, **options):
        tournament_id = options["tournament"]
        round_number = options["round"]

        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tournament {tournament_id} not found"))
            return

        groups = Group.objects.filter(tournament=tournament, round_number=round_number)
        total_completed = 0

        with transaction.atomic():
            for group in groups:
                if group.status == "completed":
                    continue

                teams = list(group.teams.all())
                if len(teams) != 2:
                    # only handle 2-team head-to-head groups
                    continue

                team_a = teams[0]
                team_b = teams[1]

                for match in group.matches.all().order_by("match_number"):
                    # Start match
                    if match.status == "waiting":
                        match.match_id = match.match_id or f"AUTO-{match.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                        match.match_password = "" if tournament.requires_password() is False else match.match_password
                        match.status = "ongoing"
                        match.started_at = timezone.now()
                        match.save()

                    # End match
                    match.status = "completed"
                    match.ended_at = timezone.now()
                    match.save()

                    # Create deterministic scores: team_a wins match 1 and 3, team_b wins match 2
                    # Determine winner pattern by match_number
                    if match.match_number in [1, 3]:
                        winner_reg = team_a
                        loser_reg = team_b
                    else:
                        winner_reg = team_b
                        loser_reg = team_a

                    # Avoid duplicate scores
                    if not MatchScore.objects.filter(match=match, team=winner_reg).exists():
                        MatchScore.objects.create(
                            match=match,
                            team=winner_reg,
                            wins=1,
                            position_points=13,
                            kill_points=25,
                        )

                    if not MatchScore.objects.filter(match=match, team=loser_reg).exists():
                        MatchScore.objects.create(
                            match=match,
                            team=loser_reg,
                            wins=0,
                            position_points=8,
                            kill_points=18,
                        )

                    # Determine match winner and update round aggregates
                    match.determine_winner()
                    TournamentGroupService.calculate_round_scores(tournament, round_number)

                # After all matches: determine group winner and mark completed
                group.determine_group_winner()
                group.status = "completed"
                group.save()
                total_completed += 1

        self.stdout.write(self.style.SUCCESS(f"Completed {total_completed} groups for tournament {tournament_id} round {round_number}"))