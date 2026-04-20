from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User


class Command(BaseCommand):
    help = "Create a test BGMI scrim for kishan@qodet.com"

    def handle(self, *args, **options):
        from tournaments.models import Tournament

        self.stdout.write("Creating test BGMI scrim for kishan@qodet.com...")

        try:
            host_user = User.objects.get(email="kishan@qodet.com")
            self.stdout.write(self.style.SUCCESS(f"Found host: {host_user.email}"))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("Host kishan@qodet.com not found!"))
            return

        try:
            host_profile = host_user.host_profile
        except Exception:
            self.stdout.write(self.style.ERROR("Host profile not found for kishan@qodet.com!"))
            return

        now = timezone.now()
        today = now.date()

        scrim = Tournament.objects.create(
            event_mode="SCRIM",
            host=host_profile,
            title="Test BGMI Scrim #1",
            description="Test scrim for development and testing purposes",
            game_name="BGMI",
            game_mode="Squad",
            max_participants=12,
            entry_fee=0,
            prize_pool=0,
            max_matches=3,
            rules="Standard BGMI scrim rules apply.",
            tournament_date=today + timedelta(days=2),
            tournament_time="20:00:00",
            registration_start=now,
            registration_end=now + timedelta(days=1),
            tournament_start=now + timedelta(days=2),
            tournament_end=now + timedelta(days=3),
            status="upcoming",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created test scrim: '{scrim.title}' (ID: {scrim.id})"
            )
        )
        self.stdout.write(f"  event_mode      : {scrim.event_mode}")
        self.stdout.write(f"  game            : {scrim.game_name} / {scrim.game_mode}")
        self.stdout.write(f"  max_participants: {scrim.max_participants}")
        self.stdout.write(f"  max_matches     : {scrim.max_matches}")
        self.stdout.write(f"  tournament_date : {scrim.tournament_date}")
        self.stdout.write(f"  registration_end: {scrim.registration_end}")
