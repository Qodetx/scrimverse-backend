from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from django.contrib.auth import get_user_model

from accounts.models import PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration


class Command(BaseCommand):
    help = "Create test players, teams and tournament registrations"

    def add_arguments(self, parser):
        parser.add_argument("--tournament", type=int, required=True, help="Tournament ID to register into")
        parser.add_argument("--teams", type=int, default=20, help="Number of teams to create")
        parser.add_argument("--players_per_team", type=int, default=5, help="Players per team")

    def handle(self, *args, **options):
        User = get_user_model()
        tournament_id = options["tournament"]
        teams = options["teams"]
        players_per_team = options["players_per_team"]

        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tournament {tournament_id} not found"))
            return

        created_users = []
        created_regs = []

        global_idx = 1
        with transaction.atomic():
            for t in range(1, teams + 1):
                team_name = f"TestTeam_{t}"
                players = []
                for p in range(1, players_per_team + 1):
                    username = f"tt{t}_p{p}"
                    email = f"{username}@example.com"
                    password = "Testpass123!"

                    # Create user if not exists
                    user, created = User.objects.get_or_create(
                        username=username,
                        defaults={
                            "email": email,
                            "user_type": "player",
                            "phone_number": "9999999999",
                        },
                    )
                    if created:
                        user.set_password(password)
                        user.save()

                    # Create PlayerProfile if not exists
                    if not hasattr(user, "player_profile"):
                        PlayerProfile.objects.create(user=user)

                    players.append(user)
                    created_users.append(user)

                # Create Team (temporary)
                captain = players[0]
                team_obj, _ = Team.objects.get_or_create(name=team_name, defaults={"captain": captain, "is_temporary": True})

                # Ensure TeamMember entries
                for idx, u in enumerate(players):
                    TeamMember.objects.get_or_create(
                        team=team_obj,
                        username=u.username,
                        defaults={"user": u, "is_captain": idx == 0},
                    )

                # Create TournamentRegistration for captain (unique per tournament)
                captain_profile = captain.player_profile
                team_members_payload = []
                for u in players:
                    team_members_payload.append({"id": u.player_profile.id, "username": u.username})

                reg, created = TournamentRegistration.objects.get_or_create(
                    tournament=tournament,
                    player=captain_profile,
                    defaults={
                        "team": team_obj,
                        "team_name": team_name,
                        "team_members": team_members_payload,
                        "status": "confirmed",
                        "payment_status": True,
                        "is_team_created": True,
                    },
                )

                if created:
                    created_regs.append(reg)

                # Increment current participants (only if registration was newly created)
                if created:
                    tournament.current_participants = (tournament.current_participants or 0) + 1

            tournament.save(update_fields=["current_participants"])

        self.stdout.write(self.style.SUCCESS(f"Created {len(created_users)} users and {len(created_regs)} registrations for tournament {tournament_id}"))