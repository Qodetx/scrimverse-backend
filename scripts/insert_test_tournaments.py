#!/usr/bin/env python
import os
import django
from datetime import timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import HostProfile
from tournaments.models import Tournament

User = get_user_model()

# Find or create a host profile
host = None
try:
    host = HostProfile.objects.first()
    if host:
        print(f"Using host: {host.user.username} (id={host.id})")
    else:
        # Try to find any user and create a HostProfile
        user = User.objects.filter(is_active=True).first()
        if not user:
            print("No users found in DB. Please create a user first.")
            exit(1)
        host = HostProfile.objects.create(user=user, organization_name=f"{user.username} Host")
        print(f"Created host profile for user {user.username}")
except Exception as e:
    print('Error finding/creating host profile:', e)
    exit(1)

now = timezone.now()

examples = [
    {
        'title': 'BGMI Duo Free Tournament',
        'game_name': 'BGMI',
        'game_mode': '2v2',
        'entry_fee': 0,
        'prize_pool': 500,
        'max_participants': 8,
    },
    {
        'title': 'BGMI Squad Paid Tournament',
        'game_name': 'BGMI',
        'game_mode': '4v4',
        'entry_fee': 50,
        'prize_pool': 2000,
        'max_participants': 20,
    },
    {
        'title': 'Valorant 5v5 Tournament',
        'game_name': 'Valorant',
        'game_mode': '5v5',
        'entry_fee': 100,
        'prize_pool': 10000,
        'max_participants': 40,
    },
    {
        'title': 'COD 5v5 Test',
        'game_name': 'COD',
        'game_mode': '5v5',
        'entry_fee': 0,
        'prize_pool': 5000,
        'max_participants': 30,
    },
]

created = []
for ex in examples:
    data = {
        'host': host,
        'title': ex['title'],
        'game_name': ex['game_name'],
        'game_mode': ex['game_mode'],
        'description': ex['title'] + ' - auto-generated for local testing',
        'max_participants': ex['max_participants'],
        'entry_fee': ex['entry_fee'],
        'prize_pool': ex['prize_pool'],
        'registration_start': now - timedelta(days=1),
        'registration_end': now + timedelta(days=7),
        'tournament_start': now + timedelta(days=8),
        'tournament_end': now + timedelta(days=10),
        'status': 'upcoming',
        'current_round': 0,
        'rules': 'Auto-generated test rules.',
    }
    try:
        t = Tournament.objects.create(**data)
        created.append(t)
        print(f"Created tournament: {t.title} (id={t.id}) mode={t.game_mode} entry_fee={t.entry_fee}")
    except Exception as e:
        print('Failed to create tournament', ex['title'], e)

print('\nDone. Created %d tournaments.' % len(created))
print('Visit your frontend at http://localhost:3000/tournaments or /tournaments/<id> to test.')
