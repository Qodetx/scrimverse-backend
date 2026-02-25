#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration

print("\n" + "="*80)
print("🔧 SETTING UP BULK SCHEDULE TEST SCENARIO")
print("="*80)

# Get or create player kishanbm25@gmail.com
print("\n" + "="*52)
print("👤 SETTING UP PLAYER ACCOUNT")
print("="*52)

user, created = User.objects.get_or_create(
    email='kishanbm25@gmail.com',
    defaults={
        'username': 'kishanbm25',
        'user_type': 'player',
        'is_active': True
    }
)

player_profile, created = PlayerProfile.objects.get_or_create(
    user=user,
    defaults={'in_game_name': 'KishanBM25'}
)

print(f"✅ Player Account: {user.email}")
print(f"   Username: {user.username}")
print(f"   IGN: {player_profile.in_game_name}")

# Get Tournament 71 (BGMI - has 8 teams with 32 players)
print("\n" + "="*52)
print("🏆 REGISTERING TO TOURNAMENT 71 (BGMI 4v4)")
print("="*52)

try:
    tournament = Tournament.objects.get(id=71)
    print(f"✅ Found Tournament: {tournament.title}")
    print(f"   Game: {tournament.game_name}")
    print(f"   Teams: 8")
    
    # Check if already registered
    existing_reg = TournamentRegistration.objects.filter(
        tournament=tournament,
        player=player_profile
    ).first()
    
    if existing_reg:
        print(f"   ℹ️  Already registered (Status: {existing_reg.status})")
        team = existing_reg.team
    else:
        # Get first team and register this player
        teams = Team.objects.filter(tournament_registrations__tournament=tournament).distinct()[:1]
        if teams:
            team = teams[0]
            reg = TournamentRegistration.objects.create(
                tournament=tournament,
                team=team,
                player=player_profile,
                status='approved'
            )
            print(f"   ✅ Registered to team: {team.name}")
        else:
            print("   ❌ No teams found in tournament")
            exit()
    
    print(f"\n   Team Details: {team.name}")
    print(f"   Players in team: {TournamentRegistration.objects.filter(tournament=tournament, team=team).count()}")
    
except Tournament.DoesNotExist:
    print("❌ Tournament 71 not found")
    exit()

# Get host for comparison
print("\n" + "="*52)
print("🏠 HOST ACCOUNT")
print("="*52)

try:
    host_user = User.objects.get(email='kishan@qodet.com')
    print(f"✅ Host: {host_user.email}")
    print(f"   Username: {host_user.username}")
except User.DoesNotExist:
    print("❌ Host not found")

print("\n" + "="*80)
print("✅ TEST SETUP COMPLETE!")
print("="*80)
print(f"""
TESTING SCENARIO:
================

Host Dashboard:
- URL: http://localhost:3000/host/dashboard
- Account: kishan@qodet.com (password: your_password)
- Tournament: Tournament 71 (BGMI Squad 4v4 Test Tournament)
- Teams: 8 teams with 4 players each

Player Dashboard:
- URL: http://localhost:3000/tournaments/71/dashboard
- Account: kishanbm25@gmail.com (password: your_password)
- Player is in: {team.name}
- View bulk schedule info from player perspective

TEST STEPS:
===========
1. Host logs in → Dashboard
2. Host goes to Tournament 71 → Manage
3. Host clicks "Start Round 1"
4. Host configures round (e.g., 2 groups of 4 teams)
5. Host uses "Bulk Schedule" feature to set:
   - Date
   - Time
   - Map for each/all groups
6. Player (kishanbm25) logs in
7. Player navigates to Tournament 71 → Matches/Schedule
8. Player should see the bulk schedule info displayed without affecting match logic
9. Verify schedule appears as INFO ONLY (no match triggers, no logic changes)

KEY VERIFICATION:
=================
✓ Bulk schedule shows date/time/map only
✓ Player can see schedule on dashboard
✓ Schedule does NOT affect:
  - Match creation
  - Round progression
  - Tournament logic
  - Match timing/lobbies
✓ Works like IDP (just informational display)
""")
