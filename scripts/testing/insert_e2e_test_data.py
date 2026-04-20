"""
E2E Testing Script: Insert Test Tournaments & Scrim
Creates:
  1. A free BGMI Squad tournament (registration open)
  2. A free Valorant 5v5 tournament (registration open)
  3. A free BGMI Scrim (registration open)

Safe to run multiple times — uses get_or_create on title to avoid duplicates.
Run from: scrimverse-backend directory
Usage: python scripts/testing/insert_e2e_test_data.py
"""

import os
import django
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from accounts.models import HostProfile, User
from tournaments.models import Tournament

now = timezone.now()

# ── Create or reuse a test host ────────────────────────────────────────────────
host_user, created = User.objects.get_or_create(
    username='e2e_test_host',
    defaults={
        'email': 'e2e_host@scrimverse.local',
        'user_type': 'host',
        'is_active': True,
    }
)
if created:
    host_user.set_password('TestHost@123')
    host_user.save()
    print(f"✅ Created test host user: e2e_test_host")
else:
    print(f"ℹ️  Reusing existing test host: e2e_test_host (ID: {host_user.id})")

host_profile, _ = HostProfile.objects.get_or_create(
    user=host_user,
    defaults={
        'bio': 'E2E Test Host — do not delete',
        'verified': True,
    }
)

# ── Tournament definitions ──────────────────────────────────────────────────────
tournaments_to_create = [
    {
        'title': '[E2E] BGMI Squad Tournament - Free',
        'event_mode': 'TOURNAMENT',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'description': 'E2E test tournament for BGMI Squad. Free entry. Registration open.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('10000.00'),
        'rules': 'Standard BGMI rules apply. Test tournament.',
        'registration_start': now - timedelta(hours=2),
        'registration_end': now + timedelta(days=7),
        'tournament_date': (now + timedelta(days=5)).date(),
        'tournament_time': (now + timedelta(days=5)).time(),
        'tournament_start': now + timedelta(days=5),
        'tournament_end': now + timedelta(days=6),
        'max_participants': 25,
        'rounds': [
            {'round': 1, 'max_teams': 25, 'qualifying_teams': 12},
            {'round': 2, 'max_teams': 12, 'qualifying_teams': 1},
        ],
        'round_names': {
            '1': 'Qualifiers',
            '2': 'Grand Finals',
        },
        'credential_release_time': now + timedelta(days=5, hours=-1),
        'slot_list_release_time': now + timedelta(days=5, hours=-2),
        'status': 'upcoming',
        'plan_payment_status': True,
    },
    {
        'title': '[E2E] Valorant 5v5 Tournament - Free',
        'event_mode': 'TOURNAMENT',
        'game_name': 'Valorant',
        'game_mode': '5v5',
        'description': 'E2E test tournament for Valorant 5v5. Free entry. Registration open.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('5000.00'),
        'rules': 'Standard Valorant rules. Test tournament.',
        'registration_start': now - timedelta(hours=1),
        'registration_end': now + timedelta(days=7),
        'tournament_date': (now + timedelta(days=6)).date(),
        'tournament_time': (now + timedelta(days=6)).time(),
        'tournament_start': now + timedelta(days=6),
        'tournament_end': now + timedelta(days=7),
        'max_participants': 16,
        'rounds': [
            {'round': 1, 'max_teams': 16, 'qualifying_teams': 4},
            {'round': 2, 'max_teams': 4, 'qualifying_teams': 1},
        ],
        'round_names': {
            '1': 'Group Stage',
            '2': 'Finals',
        },
        'credential_release_time': now + timedelta(days=6, hours=-1),
        'slot_list_release_time': now + timedelta(days=6, hours=-2),
        'status': 'upcoming',
        'plan_payment_status': True,
    },
    {
        'title': '[E2E] BGMI Squad Scrim - Free',
        'event_mode': 'SCRIM',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'description': 'E2E test scrim for BGMI Squad. Free entry. Registration open.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('0.00'),
        'rules': 'Standard BGMI scrim rules. Test scrim.',
        'registration_start': now - timedelta(hours=1),
        'registration_end': now + timedelta(days=7),
        'tournament_date': (now + timedelta(days=3)).date(),
        'tournament_time': (now + timedelta(days=3)).time(),
        'tournament_start': now + timedelta(days=3),
        'tournament_end': now + timedelta(days=3, hours=4),
        'max_participants': 25,
        'max_matches': 4,
        'rounds': [
            {'round': 1, 'max_teams': 25, 'qualifying_teams': 0},
        ],
        'credential_release_time': now + timedelta(days=3, hours=-1),
        'slot_list_release_time': now + timedelta(days=3, hours=-2),
        'status': 'upcoming',
        'plan_payment_status': True,
    },
]

print("\n" + "=" * 70)
print("  E2E Test Data Insertion")
print("=" * 70)
print(f"  Host: e2e_test_host (Profile ID: {host_profile.id})")
print(f"  Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70 + "\n")

created_count = 0
skipped_count = 0

for data in tournaments_to_create:
    title = data['title']
    existing = Tournament.objects.filter(title=title).first()

    if existing:
        print(f"ℹ️  SKIPPED (already exists): {title}")
        print(f"   ID: {existing.id} | Status: {existing.status}")
        skipped_count += 1
        continue

    try:
        t = Tournament.objects.create(host=host_profile, **data)
        created_count += 1
        print(f"✅ CREATED: {t.title}")
        print(f"   ID: {t.id}")
        print(f"   Mode: {t.event_mode} | Game: {t.game_name} ({t.game_mode})")
        print(f"   Entry Fee: ₹{t.entry_fee} | Max Teams: {t.max_participants}")
        print(f"   Reg Window: {t.registration_start.strftime('%d %b %H:%M')} → {t.registration_end.strftime('%d %b %H:%M')}")
    except Exception as e:
        print(f"❌ FAILED: {title}")
        print(f"   Error: {e}")
    print()

print("=" * 70)
print(f"  Done — Created: {created_count} | Skipped: {skipped_count}")
print("=" * 70)
print("""
Next Steps:
  1. Go to http://localhost:3000/tournaments
  2. Look for tournaments starting with '[E2E]'
  3. Go to http://localhost:3000/scrims (or Scrims tab)
  4. Look for scrims starting with '[E2E]'
""")
