"""
Test Script: Create Free Tournaments for Testing Mandatory Teammate Emails
This script creates test tournaments with 0 entry fee and open registration windows.
Safe to run - only creates new tournaments, doesn't affect existing ones.
"""

import os
import django
from datetime import datetime, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from accounts.models import HostProfile, User
from tournaments.models import Tournament

# Create or get a test host
host_user, _ = User.objects.get_or_create(
    username='test_host_free_tournaments',
    defaults={
        'email': 'testhost@scrimverse.local',
        'user_type': 'host',
        'is_active': True
    }
)

host_profile, _ = HostProfile.objects.get_or_create(
    user=host_user,
    defaults={
        'bio': 'Test Host for Free Tournament Testing',
        'verified': True
    }
)

now = timezone.now()

# Define test tournaments
test_tournaments = [
    {
        'title': '[TEST] BGMI Squad - FREE - Mandatory Emails Test',
        'game_name': 'BGMI',
        'game_mode': 'Squad',  # 4 players (3 teammates + captain)
        'description': 'Free BGMI tournament to test mandatory teammate email registration.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('0.00'),
        'rules': 'Test tournament for mandatory email validation.',
        'registration_start': now - timedelta(hours=1),  # Started 1 hour ago
        'registration_end': now + timedelta(days=7),      # Open for next 7 days
        'tournament_date': (now + timedelta(days=3)).date(),
        'tournament_time': (now + timedelta(days=3)).time(),
        'tournament_start': now + timedelta(days=3),      # Start in 3 days
        'tournament_end': now + timedelta(days=4),        # End next day
        'max_participants': 20,
        'rounds': [
            {
                'round': 1,
                'max_teams': 20,
                'qualifying_teams': 10
            },
            {
                'round': 2,
                'max_teams': 10,
                'qualifying_teams': 4
            }
        ],
        'round_names': {
            '1': 'Qualifiers',
            '2': 'Finals'
        }
    },
    {
        'title': '[TEST] COD 5v5 - FREE - Mandatory Emails Test',
        'game_name': 'COD',
        'game_mode': '5v5',  # 5 players (4 teammates + captain)
        'description': 'Free COD tournament to test mandatory 4 teammate emails registration.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('0.00'),
        'rules': 'Test tournament for 5v5 mandatory email validation.',
        'registration_start': now - timedelta(hours=2),   # Started 2 hours ago
        'registration_end': now + timedelta(days=7),      # Open for next 7 days
        'tournament_date': (now + timedelta(days=5)).date(),
        'tournament_time': (now + timedelta(days=5)).time(),
        'tournament_start': now + timedelta(days=5),      # Start in 5 days
        'tournament_end': now + timedelta(days=6),        # End next day
        'max_participants': 16,
        'rounds': [
            {
                'round': 1,
                'max_teams': 16,
                'qualifying_teams': 8
            },
            {
                'round': 2,
                'max_teams': 8,
                'qualifying_teams': 2
            }
        ],
        'round_names': {
            '1': 'Group Stage',
            '2': 'Finals'
        }
    },
    {
        'title': '[TEST] Valorant 5v5 - FREE - Mandatory Emails Test',
        'game_name': 'Valorant',
        'game_mode': '5v5',  # 5 players (4 teammates + captain)
        'description': 'Free Valorant tournament to test mandatory 4 teammate emails registration.',
        'entry_fee': Decimal('0.00'),
        'prize_pool': Decimal('0.00'),
        'rules': 'Test tournament for 5v5 mandatory email validation.',
        'registration_start': now - timedelta(hours=3),   # Started 3 hours ago
        'registration_end': now + timedelta(days=7),      # Open for next 7 days
        'tournament_date': (now + timedelta(days=4)).date(),
        'tournament_time': (now + timedelta(days=4)).time(),
        'tournament_start': now + timedelta(days=4),      # Start in 4 days
        'tournament_end': now + timedelta(days=5),        # End next day
        'max_participants': 16,
        'rounds': [
            {
                'round': 1,
                'max_teams': 16,
                'qualifying_teams': 8
            },
            {
                'round': 2,
                'max_teams': 8,
                'qualifying_teams': 2
            }
        ],
        'round_names': {
            '1': 'Group Stage',
            '2': 'Finals'
        }
    }
]

print("=" * 80)
print("Creating Free Test Tournaments for Mandatory Teammate Email Testing")
print("=" * 80)
print(f"\nTest Host: test_host_free_tournaments (ID: {host_profile.id})")
print(f"Current Time: {now}")
print()

created_count = 0
for tournament_data in test_tournaments:
    try:
        tournament = Tournament.objects.create(
            host=host_profile,
            **tournament_data
        )
        created_count += 1
        
        print(f"✅ Created: {tournament.title}")
        print(f"   ID: {tournament.id}")
        print(f"   Game: {tournament.game_name} ({tournament.game_mode})")
        print(f"   Entry Fee: ₹{tournament.entry_fee}")
        print(f"   Registration: {tournament.registration_start.strftime('%Y-%m-%d %H:%M')} to {tournament.registration_end.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Max Participants: {tournament.max_participants}")
        print()
        
    except Exception as e:
        print(f"❌ Failed to create: {tournament_data['title']}")
        print(f"   Error: {str(e)}")
        print()

print("=" * 80)
print(f"Summary: Created {created_count} test tournament(s)")
print("=" * 80)
print("""
TESTING GUIDE:
1. Go to http://localhost:3000/tournaments
2. Find tournaments starting with "[TEST]"
3. Click "Join Tournament"
4. Test scenarios:
   - BGMI: Try registering with only 1-2 teammate emails (should fail)
              Try with 3 teammate emails (should succeed)
   - COD/Valorant: Try with only 2-3 emails (should fail)
                   Try with 4 emails (should succeed)
5. Verify error messages for incomplete registrations
6. Test free tournament registration (should confirm immediately)
7. Verify teammate invitation emails are created
8. Check invited_members_status is populated correctly

NOTES:
- These are FREE tournaments (₹0 entry fee)
- Registration is open for 7 days
- You can delete these tournaments after testing via Django admin
- Look for tournament IDs above to find them easily
""")
