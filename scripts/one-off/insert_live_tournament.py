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
    print("Host with ID 1 not found. Creating test host...")
    from accounts.models import User
    user = User.objects.create_user(username='testhost', email='host@test.com', password='test123')
    host = HostProfile.objects.create(user=user)
    print(f"Created host: {host.user.username}")

# Create a live tournament
now = timezone.now()
tournament_data = {
    'host': host,
    'title': 'Live Valorant Tournament',
    'game_name': 'Valorant',
    'game_mode': '5v5',
    'description': 'This is a live tournament for testing purposes.',
    'max_participants': 10,
    'entry_fee': 100,
    'prize_pool': 1000,
    'registration_start': now - timedelta(days=7),
    'registration_end': now + timedelta(days=1),
    'tournament_start': now - timedelta(minutes=5),  # Started 5 minutes ago
    'tournament_end': now + timedelta(days=2),
    'status': 'ongoing',  # Already live!
    'current_round': 1,
    'rules': 'Standard tournament rules apply. No cheating, no exploits.',
    'round_status': {'1': 'ongoing'},
    'rounds': [
        {'round': 1, 'max_teams': 10, 'qualifying_teams': 5},
        {'round': 2, 'max_teams': 5, 'qualifying_teams': 2},
        {'round': 3, 'max_teams': 2, 'qualifying_teams': 1},
    ],
    'placement_points': {'1': 15, '2': 12, '3': 10, '4': 8, '5': 6},
}

tournament = Tournament.objects.create(**tournament_data)
print(f"\n✅ Created live tournament: {tournament.title}")
print(f"   ID: {tournament.id}")
print(f"   Status: {tournament.status}")
print(f"   Current Round: {tournament.current_round}")
print(f"   Started: {tournament.tournament_start}")
print(f"   Host: {tournament.host.user.username}")
print(f"\n🎮 Tournament is NOW LIVE and ready to manage!")
print(f"   Navigate to: http://localhost:3000/tournaments/{tournament.id}/manage")
