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
                if not teams:
                    continue

                for match in group.matches.all().order_by("match_number"):
                    # Start match
                    if match.status == "waiting":
                        match.match_id = match.match_id or f"AUTO-{match.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                        match.status = "ongoing"
                        match.started_at = timezone.now()
                        match.save()

                    # End match
                    match.status = "completed"
                    match.ended_at = timezone.now()
                    match.save()

                    # Give each team deterministic scores varying by position
                    for i, team in enumerate(teams):
                        if MatchScore.objects.filter(match=match, team=team).exists():
                            continue
                        # First team gets highest points, descending
                        MatchScore.objects.create(
                            match=match,
                            team=team,
                            wins=1 if i == 0 else 0,
                            position_points=max(1, 15 - i * 2),
                            kill_points=max(0, 20 - i * 3),
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