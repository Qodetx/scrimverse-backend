"""
Seed analytics test data for test_esports_hub host.

Creates:
- 5 tournaments across 4 games (BGMI x2, Valorant, Free Fire, COD Mobile)
  - 2 completed, 2 upcoming, 1 ongoing
- 8-20 confirmed registrations per tournament
  - registered_at dates spread across last 6 months
- Completed entry_fee Payment records for paid tournaments
  - completed_at spread across last 6 months
- Some players registered to multiple tournaments (returning player data)

Run:
  python manage.py seed_host_analytics
  python manage.py seed_host_analytics --host testhost1@gmail.com
  python manage.py seed_host_analytics --flush  # delete seed data first
"""

import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import HostProfile, PlayerProfile, Team, TeamMember
from payments.models import Payment
from tournaments.models import Tournament, TournamentRegistration

User = get_user_model()

SEED_TAG = "seed_analytics_"

TOURNAMENT_SPECS = [
    {
        "title": "BGMI Season 1 — Open Qualifier",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 20,
        "entry_fee": 150,
        "prize_pool": 15000,
        "status": "completed",
        "months_ago": 5,
        "team_count": 20,
    },
    {
        "title": "Free Fire Clash Cup",
        "game_name": "Free Fire",
        "game_mode": "Squad",
        "max_participants": 16,
        "entry_fee": 100,
        "prize_pool": 8000,
        "status": "completed",
        "months_ago": 3,
        "team_count": 14,
    },
    {
        "title": "Valorant 5v5 Invitational",
        "game_name": "Valorant",
        "game_mode": "5v5",
        "max_participants": 8,
        "entry_fee": 200,
        "prize_pool": 20000,
        "status": "ongoing",
        "months_ago": 0,
        "team_count": 8,
    },
    {
        "title": "BGMI Season 2 — Pro League",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 24,
        "entry_fee": 250,
        "prize_pool": 30000,
        "status": "upcoming",
        "months_ago": -1,
        "team_count": 18,
    },
    {
        "title": "COD Mobile Friday Fights",
        "game_name": "COD Mobile",
        "game_mode": "5v5",
        "max_participants": 12,
        "entry_fee": 0,
        "prize_pool": 5000,
        "status": "upcoming",
        "months_ago": -2,
        "team_count": 10,
    },
]


class Command(BaseCommand):
    help = "Seed analytics test data for a host account"

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            default="testhost1@gmail.com",
            help="Host email (default: testhost1@gmail.com)",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously seeded data before creating new data",
        )

    def handle(self, *args, **options):
        host_email = options["host"]
        flush = options["flush"]

        # ── Get host ──────────────────────────────────────────────────────────
        try:
            host_user = User.objects.get(email=host_email)
            host_profile = host_user.host_profile
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User not found: {host_email}"))
            return
        except Exception:
            self.stderr.write(self.style.ERROR(f"No host profile for {host_email}"))
            return

        self.stdout.write(f"Host: {host_user.username} ({host_email})")

        # ── Flush ─────────────────────────────────────────────────────────────
        if flush:
            deleted_t = Tournament.objects.filter(
                host=host_profile, title__startswith=SEED_TAG
            ).delete()
            # Also clean up seeded users
            User.objects.filter(username__startswith=SEED_TAG).delete()
            self.stdout.write(self.style.WARNING(f"Flushed previous seed data: {deleted_t}"))

        now = timezone.now()
        created_tournaments = []

        for spec in TOURNAMENT_SPECS:
            months_ago = spec["months_ago"]
            base_date = now - timedelta(days=abs(months_ago) * 30) if months_ago >= 0 else now + timedelta(days=abs(months_ago) * 30)

            # Tournament dates
            if spec["status"] == "completed":
                t_start = base_date - timedelta(days=2)
                t_end = base_date
                reg_start = base_date - timedelta(days=14)
                reg_end = base_date - timedelta(days=3)
            elif spec["status"] == "ongoing":
                t_start = now - timedelta(hours=6)
                t_end = now + timedelta(days=1)
                reg_start = now - timedelta(days=10)
                reg_end = now - timedelta(days=1)
            else:  # upcoming
                t_start = base_date + timedelta(days=7)
                t_end = base_date + timedelta(days=8)
                reg_start = now - timedelta(days=3)
                reg_end = base_date + timedelta(days=5)

            full_title = SEED_TAG + spec["title"]
            tournament, created = Tournament.objects.get_or_create(
                host=host_profile,
                title=full_title,
                defaults={
                    "description": f"Seeded test tournament — {spec['title']}",
                    "game_name": spec["game_name"],
                    "game_mode": spec["game_mode"],
                    "max_participants": spec["max_participants"],
                    "current_participants": 0,
                    "entry_fee": spec["entry_fee"],
                    "prize_pool": spec["prize_pool"],
                    "tournament_date": t_start.date(),
                    "tournament_time": t_start.time(),
                    "registration_start": reg_start,
                    "registration_end": reg_end,
                    "tournament_start": t_start,
                    "tournament_end": t_end,
                    "rules": "Seeded test data — standard rules apply.",
                    "status": spec["status"],
                    "plan_payment_status": True,
                    "plan_payment_id": f"SEED_{uuid.uuid4().hex[:8].upper()}",
                },
            )

            if created:
                self.stdout.write(f"  Created tournament: {spec['title']} [{spec['status']}]")
            else:
                self.stdout.write(
                    self.style.WARNING(f"  Already exists: {spec['title']} — skipping registrations")
                )
                created_tournaments.append((tournament, spec, base_date))
                continue

            created_tournaments.append((tournament, spec, base_date))

            # ── Create teams + registrations ──────────────────────────────────
            team_count = spec["team_count"]
            registered_at_spread = []
            # Spread registrations across the reg window
            if spec["status"] in ("completed", "ongoing"):
                window_days = (reg_end - reg_start).days or 1
                for i in range(team_count):
                    offset = random.randint(0, window_days)
                    registered_at_spread.append(reg_start + timedelta(days=offset))
            else:
                for i in range(team_count):
                    offset = random.randint(0, 2)
                    registered_at_spread.append(now - timedelta(days=offset))

            for team_idx in range(team_count):
                slug = f"{SEED_TAG}t{tournament.id}_tm{team_idx + 1}"

                # Captain
                cap_username = f"{slug}_cap"
                cap_user, _ = User.objects.get_or_create(
                    username=cap_username,
                    defaults={
                        "email": f"{cap_username}@seed.test",
                        "user_type": "player",
                        "phone_number": f"7{tournament.id:03d}{team_idx:05d}",
                        "is_active": True,
                    },
                )
                if _:
                    cap_user.set_password("Seedpass123!")
                    cap_user.save()

                cap_profile, _ = PlayerProfile.objects.get_or_create(user=cap_user)

                # Team
                team_name = f"Seed Team {tournament.id}-{team_idx + 1}"
                team_obj, _ = Team.objects.get_or_create(
                    name=team_name,
                    defaults={"captain": cap_user, "is_temporary": True},
                )
                TeamMember.objects.get_or_create(
                    team=team_obj,
                    username=cap_username,
                    defaults={"user": cap_user, "is_captain": True},
                )

                reg_time = registered_at_spread[team_idx]

                # Registration
                reg, reg_created = TournamentRegistration.objects.get_or_create(
                    tournament=tournament,
                    player=cap_profile,
                    defaults={
                        "team": team_obj,
                        "team_name": team_name,
                        "status": "confirmed",
                        "payment_status": spec["entry_fee"] > 0,
                        "is_team_created": True,
                        "registered_at": reg_time,
                    },
                )

                if reg_created and spec["entry_fee"] > 0:
                    # Create a completed payment record
                    pay_completed_at = reg_time + timedelta(minutes=random.randint(1, 15))
                    Payment.objects.create(
                        user=cap_user,
                        tournament=tournament,
                        payment_type="entry_fee",
                        amount=Decimal(str(spec["entry_fee"])),
                        amount_paisa=int(spec["entry_fee"] * 100),
                        merchant_order_id=f"SEED_{uuid.uuid4().hex[:16].upper()}",
                        status="completed",
                        completed_at=pay_completed_at,
                    )

            # Update participant count
            confirmed_count = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).count()
            tournament.current_participants = confirmed_count
            tournament.save(update_fields=["current_participants"])

            revenue_note = (
                f", Rs.{confirmed_count * spec['entry_fee']} revenue" if spec["entry_fee"] > 0 else ", free entry"
            )
            self.stdout.write(f"    {confirmed_count} registrations{revenue_note}")

        # ── Cross-tournament returning player: register some cap users from T1 into T4 ──
        t1 = next((t for t, s, _ in created_tournaments if "Season 1" in s["title"]), None)
        t4 = next((t for t, s, _ in created_tournaments if "Season 2" in s["title"]), None)
        if t1 and t4:
            t4_capacity = t4.max_participants or 0
            t4_confirmed = TournamentRegistration.objects.filter(tournament=t4, status="confirmed").count()
            slots_left = max(0, t4_capacity - t4_confirmed)
            carry_limit = min(6, slots_left)
            t1_regs = list(
                TournamentRegistration.objects.filter(tournament=t1, status="confirmed").select_related("player__user")[:carry_limit]
            )
            carry_count = 0
            for reg in t1_regs:
                existing = TournamentRegistration.objects.filter(tournament=t4, player=reg.player).exists()
                if not existing:
                    new_team_name = f"Returning Team {reg.player.id}"
                    new_team, _ = Team.objects.get_or_create(
                        name=new_team_name,
                        defaults={"captain": reg.player.user, "is_temporary": True},
                    )
                    TournamentRegistration.objects.create(
                        tournament=t4,
                        player=reg.player,
                        team=new_team,
                        team_name=new_team_name,
                        status="confirmed",
                        payment_status=True,
                        is_team_created=True,
                        registered_at=now - timedelta(days=random.randint(0, 2)),
                    )
                    # Payment for returning player
                    Payment.objects.create(
                        user=reg.player.user,
                        tournament=t4,
                        payment_type="entry_fee",
                        amount=Decimal("250"),
                        amount_paisa=25000,
                        merchant_order_id=f"SEED_{uuid.uuid4().hex[:16].upper()}",
                        status="completed",
                        completed_at=now - timedelta(days=random.randint(0, 1)),
                    )
                    carry_count += 1

            # Update t4 participant count
            t4.current_participants = TournamentRegistration.objects.filter(
                tournament=t4, status="confirmed"
            ).count()
            t4.save(update_fields=["current_participants"])
            self.stdout.write(f"  Carried {carry_count} returning players from Season 1 into Season 2")

        self.stdout.write(self.style.SUCCESS("\nAnalytics seed complete!"))
        self.stdout.write("Go to /host/dashboard Analytics tab to verify data.")
