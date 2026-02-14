#!/usr/bin/env python
import os
import django
from datetime import datetime, timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import HostProfile
from tournaments.models import Tournament

# Get host with ID 1
try:
    host = HostProfile.objects.get(id=1)
    print(f"Found host: {host.user.username}")
except HostProfile.DoesNotExist:
    print("Host with ID 1 not found.")
    exit(1)

# Helper function to create tournament
def create_tournament(title, game_name, game_mode, is_5v5=False):
    now = timezone.now()
    tournament_data = {
        'host': host,
        'title': title,
        'game_name': game_name,
        'game_mode': game_mode,
        'description': f'{game_name} {game_mode} tournament for testing registration flow.',
        'max_participants': 10 if is_5v5 else 8,
        'entry_fee': 100,
        'prize_pool': 1000,
        'registration_start': now,
        'registration_end': now + timedelta(days=7),
        'tournament_start': now + timedelta(days=8),
        'tournament_end': now + timedelta(days=10),
        'status': 'upcoming',
        'current_round': 0,
        'rules': 'Standard rules apply.',
        'round_status': {},
        'rounds': [
            {'round': 1, 'max_teams': 10, 'qualifying_teams': 5},
            {'round': 2, 'max_teams': 5, 'qualifying_teams': 2},
            {'round': 3, 'max_teams': 2, 'qualifying_teams': 1},
        ],
        'placement_points': {'1': 15, '2': 12, '3': 10, '4': 8, '5': 6},
    }
    
    tournament = Tournament.objects.create(**tournament_data)
    return tournament

# Create tournaments
print("\n📝 Creating multiple tournaments for registration flow testing...\n")

tournaments = [
    ("BGMI Squad Tournament", "BGMI", "4v4", False),
    ("BGMI Duo Tournament", "BGMI", "2v2", False),
    ("Valorant 5v5 Tournament", "Valorant", "5v5", True),
    ("Call of Duty 5v5 Tournament", "Call of Duty", "5v5", True),
]

created_tournaments = []
for title, game, mode, is_5v5 in tournaments:
    try:
        tournament = create_tournament(title, game, mode, is_5v5)
        created_tournaments.append(tournament)
        print(f"✅ {title}")
        print(f"   ID: {tournament.id}")
        print(f"   Game: {game} | Mode: {mode} | Is 5v5: {is_5v5}")
        print(f"   Status: {tournament.status}")
        print(f"   Manage: http://localhost:3000/tournaments/{tournament.id}/manage")
        print()
    except Exception as e:
        print(f"❌ Failed to create {title}: {e}\n")

print(f"\n🎮 Total tournaments created: {len(created_tournaments)}")
print("\nNow test registration form:")
print("1. Go to http://localhost:3000/tournaments and view the live tournaments")
print("2. Click 'Register' on each tournament and verify teammate fields:")
print("   - BGMI Squad: 3 teammate email fields (total 4 players)")
print("   - BGMI Duo: 1 teammate email field (total 2 players)")
print("   - Valorant 5v5: 4 teammate email fields (total 5 players)")
print("   - Call of Duty 5v5: 4 teammate email fields (total 5 players)")
