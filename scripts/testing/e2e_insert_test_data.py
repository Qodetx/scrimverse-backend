"""
E2E Tournament Insert Script
-----------------------------
Only inserts test tournaments using the existing host: kishan@qodet.com
Does NOT create any player users - those are done via normal browser registration.

Run from backend root:
  python scripts/testing/e2e_insert_test_data.py
"""

import os
import django
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import HostProfile
from tournaments.models import Tournament

User = get_user_model()
now = timezone.now()

print("=" * 70)
print("E2E TEST TOURNAMENT INSERT")
print("=" * 70)

# Use existing host
try:
    host_user = User.objects.get(email='kishan@qodet.com')
    host_profile = HostProfile.objects.get(user=host_user)
    print(f"\n✅ Using host: {host_user.username} (ID: {host_user.id})")
except User.DoesNotExist:
    print("❌ Host user kishan@qodet.com not found! Aborting.")
    exit(1)
except HostProfile.DoesNotExist:
    print("❌ HostProfile for kishan@qodet.com not found! Aborting.")
    exit(1)

# ─── BGMI Squad Tournament (FREE, registration open) ─────────────────────────
bgmi_tournament = Tournament.objects.create(
    host=host_profile,
    title='[E2E] BGMI Squad Championship - Free',
    game_name='BGMI',
    game_mode='Squad',
    description='Auto-created E2E test tournament. BGMI Squad, 4 players per team. Free entry. Open for testing.',
    entry_fee=Decimal('0.00'),
    prize_pool=Decimal('5000.00'),
    prize_distribution={'1st': 3000, '2nd': 1500, '3rd': 500},
    rules='Standard BGMI rules apply. Created for E2E testing.',
    registration_start=now - timedelta(hours=1),
    registration_end=now + timedelta(days=7),
    tournament_date=(now + timedelta(days=3)).date(),
    tournament_time=(now + timedelta(days=3)).time(),
    tournament_start=now + timedelta(days=3),
    tournament_end=now + timedelta(days=4),
    max_participants=25,
    rounds=[
        {'round': 1, 'max_teams': 25, 'qualifying_teams': 10},
        {'round': 2, 'max_teams': 10, 'qualifying_teams': 1},
    ],
    round_names={'1': 'Qualifiers', '2': 'Grand Finals'},
    plan_type='basic',
    plan_payment_status=True,
    status='upcoming',
)
print(f"\n✅ Tournament: '{bgmi_tournament.title}' (ID: {bgmi_tournament.id})")
print(f"   {bgmi_tournament.game_name} {bgmi_tournament.game_mode} | Entry: FREE")
print(f"   Registration open until: {bgmi_tournament.registration_end.strftime('%d %b %Y %H:%M')}")

# ─── BGMI Scrim (FREE, registration open) ────────────────────────────────────
bgmi_scrim = Tournament.objects.create(
    host=host_profile,
    title='[E2E] BGMI Practice Scrim - Free',
    event_mode='SCRIM',
    game_name='BGMI',
    game_mode='Squad',
    description='Auto-created E2E test scrim. Practice match. Free entry. Open for testing.',
    entry_fee=Decimal('0.00'),
    prize_pool=Decimal('0.00'),
    rules='Practice match. Standard BGMI rules. Created for E2E testing.',
    registration_start=now - timedelta(hours=1),
    registration_end=now + timedelta(days=3),
    tournament_date=(now + timedelta(days=1)).date(),
    tournament_time=(now + timedelta(days=1)).time(),
    tournament_start=now + timedelta(days=1),
    tournament_end=now + timedelta(days=2),
    max_participants=20,
    max_matches=4,
    plan_type='basic',
    plan_payment_status=True,
    status='upcoming',
)
print(f"\n✅ Scrim:      '{bgmi_scrim.title}' (ID: {bgmi_scrim.id})")
print(f"   {bgmi_scrim.game_name} {bgmi_scrim.game_mode} | Entry: FREE")
print(f"   Registration open until: {bgmi_scrim.registration_end.strftime('%d %b %Y %H:%M')}")

print("\n" + "=" * 70)
print("DONE. Tournaments are live at http://localhost:3000")
print(f"  Tournament ID : {bgmi_tournament.id}")
print(f"  Scrim ID      : {bgmi_scrim.id}")
print("=" * 70)
