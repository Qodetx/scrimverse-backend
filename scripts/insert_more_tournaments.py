#!/usr/bin/env python
"""
Insert additional test tournaments: 2v2 and 4v4 BGMI (free)
"""
import sys
import os
from datetime import datetime, timedelta

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()

from accounts.models import HostProfile
from tournaments.models import Tournament
from django.utils import timezone

# Get or use default host
try:
    host = HostProfile.objects.first()
except:
    print("No host found!")
    sys.exit(1)

print(f"Using host: {host.user.username} (id={host.id})")

now = timezone.now()
base_start = now + timedelta(days=7)  # 7 days from now
base_end = base_start + timedelta(hours=4)
reg_start = now + timedelta(hours=1)
reg_end = base_start - timedelta(hours=1)

tournaments_to_create = [
    {
        'title': 'BGMI 2v2 Free Tournament #1',
        'game_name': 'BGMI',
        'game_mode': 'Duo',
        'max_participants': 50,
        'entry_fee': 0,
        'prize_pool': 10000,
    },
    {
        'title': 'BGMI 2v2 Free Tournament #2',
        'game_name': 'BGMI',
        'game_mode': 'Duo',
        'max_participants': 50,
        'entry_fee': 0,
        'prize_pool': 12000,
    },
    {
        'title': 'BGMI 4v4 Free Tournament #1',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'max_participants': 32,
        'entry_fee': 0,
        'prize_pool': 15000,
    },
    {
        'title': 'BGMI 4v4 Free Tournament #2',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'max_participants': 32,
        'entry_fee': 0,
        'prize_pool': 18000,
    },
]

for config in tournaments_to_create:
    tournament = Tournament.objects.create(
        host=host,
        title=config['title'],
        description=f"Free {config['game_mode']} tournament for {config['game_name']}",
        game_name=config['game_name'],
        game_mode=config['game_mode'],
        max_participants=config['max_participants'],
        entry_fee=config['entry_fee'],
        prize_pool=config['prize_pool'],
        registration_start=reg_start,
        registration_end=reg_end,
        tournament_start=base_start,
        tournament_end=base_end,
        rules="Standard rules apply",
        rounds=[{
            'round': 1,
            'max_teams': config['max_participants'],
            'qualifying_teams': 0
        }],
        plan_type='basic',
        plan_payment_status=True,
        plan_payment_id='FREE_PLAN',
        status='upcoming',
    )
    print(f"✓ Created: {tournament.title} (id={tournament.id}) mode={tournament.game_mode} entry_fee=₹{tournament.entry_fee}")

print(f"\nDone. Created {len(tournaments_to_create)} tournaments.")
