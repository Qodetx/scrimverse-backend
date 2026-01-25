"""
Django management command to create test tournaments and scrims.
Run with: python manage.py create_test_data
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import HostProfile, User
from tournaments.models import Tournament


class Command(BaseCommand):
    help = "Creates test tournaments and scrims for all scenarios"

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Creating Test Tournaments and Scrims")
        self.stdout.write("=" * 60 + "\n")

        # Get or create host
        host = self.get_or_create_host()
        if not host:
            self.stdout.write(self.style.ERROR("\n[FAILED] Failed to create host. Exiting."))
            return

        self.stdout.write(self.style.SUCCESS(f"\n[OK] Using host: {host.user.username}\n"))

        # Delete existing test tournaments
        self.stdout.write("Cleaning up old test data...")
        Tournament.objects.filter(host=host).delete()
        self.stdout.write(self.style.SUCCESS("[OK] Cleaned up old test data\n"))

        plan_types = ["premium", "featured", "basic"]
        event_modes = [("TOURNAMENT", "Tournament"), ("SCRIM", "Scrim")]

        created_count = 0

        # Create tournaments for each scenario
        for event_mode, mode_name in event_modes:
            self.stdout.write(f"Creating {mode_name}s")
            self.stdout.write(f"{'-'*60}\n")

            for plan_type in plan_types:
                self.stdout.write(f"\n  {plan_type.upper()} Plan:")

                # UPCOMING - Registration Not Started
                tournament = self.create_tournament(host, event_mode, plan_type, "upcoming", "not_started")
                if tournament:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] Created: {tournament.title}"))
                    created_count += 1

                # UPCOMING - Registration Open
                tournament = self.create_tournament(host, event_mode, plan_type, "upcoming", "open")
                if tournament:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] Created: {tournament.title}"))
                    created_count += 1

                # UPCOMING - Registration Ended
                tournament = self.create_tournament(host, event_mode, plan_type, "upcoming", "ended")
                if tournament:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] Created: {tournament.title}"))
                    created_count += 1

                # ONGOING
                tournament = self.create_tournament(host, event_mode, plan_type, "ongoing")
                if tournament:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] Created: {tournament.title}"))
                    created_count += 1

                # COMPLETED
                tournament = self.create_tournament(host, event_mode, plan_type, "completed")
                if tournament:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] Created: {tournament.title}"))
                    created_count += 1

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"Summary: Created {created_count} test events"))
        self.stdout.write("=" * 60)

        # Print breakdown
        self.stdout.write("\nBreakdown:")
        self.stdout.write(f"  • Tournaments: {Tournament.objects.filter(host=host, event_mode='TOURNAMENT').count()}")
        self.stdout.write(f"  • Scrims: {Tournament.objects.filter(host=host, event_mode='SCRIM').count()}")
        self.stdout.write("\nBy Status:")
        self.stdout.write(f"  • Upcoming: {Tournament.objects.filter(host=host, status='upcoming').count()}")
        self.stdout.write(f"  • Ongoing: {Tournament.objects.filter(host=host, status='ongoing').count()}")
        self.stdout.write(f"  • Completed: {Tournament.objects.filter(host=host, status='completed').count()}")
        self.stdout.write("\nBy Plan Type:")
        self.stdout.write(f"  • Basic: {Tournament.objects.filter(host=host, plan_type='basic').count()}")
        self.stdout.write(f"  • Featured: {Tournament.objects.filter(host=host, plan_type='featured').count()}")
        self.stdout.write(f"  • Premium: {Tournament.objects.filter(host=host, plan_type='premium').count()}")

        self.stdout.write(self.style.SUCCESS("\n[OK] All test data created successfully!"))
        self.stdout.write("\nYou can now test:")
        self.stdout.write("  * /tournaments page")
        self.stdout.write("  * /scrims page")
        self.stdout.write("  * All badge types (basic, featured, premium)")
        self.stdout.write("  * All status types (upcoming, active, past)")
        self.stdout.write("  * All registration states (not started, open, ended)")
        self.stdout.write("\n" + "=" * 60 + "\n")

    def get_or_create_host(self):
        """Get or create a test host user."""
        try:
            host_user = User.objects.filter(user_type="host").first()
            if not host_user:
                host_user = User.objects.create_user(
                    username="testhost", email="testhost@scrimverse.com", password="testpass123", user_type="host"
                )
                self.stdout.write(self.style.SUCCESS(f"[OK] Created test host user: {host_user.username}"))

            host_profile = HostProfile.objects.filter(user=host_user).first()
            if not host_profile:
                host_profile = HostProfile.objects.create(
                    user=host_user, organization_name="Test Gaming Org", verification_status="approved"
                )
                self.stdout.write(self.style.SUCCESS(f"[OK] Created host profile for: {host_user.username}"))

            return host_profile
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[FAILED] Error creating host: {e}"))
            return None

    def create_tournament(self, host, event_mode, plan_type, status, reg_status=None):
        """Create a tournament with specific parameters."""
        now = timezone.now()

        # Set up times based on status and registration status
        if status == "upcoming":
            if reg_status == "not_started":
                reg_start = now + timedelta(days=2)
                reg_end = now + timedelta(days=5)
                tournament_start = now + timedelta(days=7)
            elif reg_status == "open":
                reg_start = now - timedelta(days=1)
                reg_end = now + timedelta(days=3)
                tournament_start = now + timedelta(days=5)
            else:  # ended
                reg_start = now - timedelta(days=5)
                reg_end = now - timedelta(days=1)
                tournament_start = now + timedelta(days=2)
        elif status == "ongoing":
            reg_start = now - timedelta(days=10)
            reg_end = now - timedelta(days=5)
            tournament_start = now - timedelta(days=1)
        else:  # completed
            reg_start = now - timedelta(days=15)
            reg_end = now - timedelta(days=10)
            tournament_start = now - timedelta(days=5)

        tournament_end = tournament_start + timedelta(hours=6)

        # Create title
        mode_name = "Scrim" if event_mode == "SCRIM" else "Tournament"
        status_name = reg_status.replace("_", " ").title() if reg_status else status.title()
        title = f"{plan_type.title()} {mode_name} - {status_name}"

        # Set max participants based on event mode
        max_participants = 25 if event_mode == "SCRIM" else 100

        # Create rounds structure as JSON
        if event_mode == "SCRIM":
            rounds_data = [{"round": 1, "max_teams": max_participants, "qualifying_teams": 0}]
        else:
            rounds_data = [
                {"round": 1, "max_teams": max_participants, "qualifying_teams": 50},
                {"round": 2, "max_teams": 50, "qualifying_teams": 20},
                {"round": 3, "max_teams": 20, "qualifying_teams": 1},
            ]

        try:
            tournament = Tournament.objects.create(
                host=host,
                title=title,
                game_name="BGMI",
                game_mode="Squad",
                prize_pool=10000 if plan_type == "basic" else (50000 if plan_type == "featured" else 100000),
                entry_fee=100 if plan_type == "basic" else (200 if plan_type == "featured" else 500),
                max_participants=max_participants,
                tournament_start=tournament_start,
                tournament_end=tournament_end,
                registration_start=reg_start,
                registration_end=reg_end,
                description=f"Test {plan_type} {mode_name.lower()} in {status} status",
                rules="Standard tournament rules apply.",
                status=status,
                event_mode=event_mode,
                plan_type=plan_type,
                is_featured=(plan_type in ["featured", "premium"]),
                current_round=1 if status == "ongoing" else 0,
                rounds=rounds_data,
            )
            return tournament
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[FAILED] Error creating {title}: {e}"))
            return None
