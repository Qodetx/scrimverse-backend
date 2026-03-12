#!/usr/bin/env python
import os
import django
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from accounts.models import HostProfile, User, Team, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration

print("\n" + "="*80)
print("🆕 CREATING NEW UPCOMING TOURNAMENT FOR BULK SCHEDULE TESTING")
print("="*80)

# Get host
try:
    host_user = User.objects.get(email='kishan@qodet.com')
    host = HostProfile.objects.get(user=host_user)
    print(f"✅ Host: {host.user.email}")
except:
    print("❌ Host not found")
    exit()

# Create new tournament (UPCOMING - not started yet)
print("\n" + "="*52)
print("🏆 CREATING UPCOMING BGMI TOURNAMENT")
print("="*52)

now = timezone.now()
tournament_start = now + timedelta(days=2)  # 2 days from now
tournament_end = now + timedelta(days=3)    # 3 days from now

tournament = Tournament.objects.create(
    host=host,
    title="BGMI Squad 4v4 - Bulk Schedule Test Tournament",
    description="Test tournament for Bulk Schedule feature - UPCOMING status",
    game_name="BGMI",
    game_mode="Squad",
    max_participants=8,
    entry_fee=0.00,
    prize_pool=0.00,
    registration_start=now,
    registration_end=now + timedelta(minutes=30),
    tournament_start=tournament_start,
    tournament_end=tournament_end,
    status="upcoming",  # IMPORTANT: Upcoming status, not completed
    use_groups_system=True,
    event_mode="TOURNAMENT",
)

# Configure rounds: 8 teams → 4 → 2 → 1
tournament.rounds = [
    {"round": 1, "max_teams": 8, "qualifying_teams": 4},
    {"round": 2, "max_teams": 4, "qualifying_teams": 2},
    {"round": 3, "max_teams": 2, "qualifying_teams": 1},
]
tournament.round_names = {
    "1": "Qualifiers",
    "2": "Semi Finals",
    "3": "Grand Finals"
}
tournament.save()

print(f"✅ Created Tournament ID {tournament.id}: {tournament.title}")
print(f"   Status: {tournament.status}")
print(f"   Start: {tournament_start}")
print(f"   End: {tournament_end}")

# Create 8 teams
print("\n" + "="*52)
print("🎯 CREATING TEAMS")
print("="*52)

teams = []
for i in range(1, 9):
    team, _ = Team.objects.get_or_create(
        name=f"Bulk Test Team {i}",
        defaults={'captain': host_user}
    )
    teams.append(team)
    print(f"  ✅ {team.name}")

# Get or create 32 players
print("\n" + "="*52)
print("👥 CREATING PLAYERS")
print("="*52)

players = []
for i in range(1, 33):
    user, _ = User.objects.get_or_create(
        username=f"bulktest_player{i}",
        defaults={'email': f'bulktest_player{i}@test.com', 'user_type': 'player'}
    )
    player, _ = PlayerProfile.objects.get_or_create(
        user=user,
        defaults={'in_game_name': f'BulkTest_{i}'}
    )
    players.append(player)

print(f"✅ Created 32 players for tournament")

# Register players to teams
print("\n" + "="*52)
print("📝 REGISTERING TEAMS & PLAYERS")
print("="*52)

player_idx = 0
for team in teams:
    for j in range(4):
        if player_idx < len(players):
            player = players[player_idx]
            TournamentRegistration.objects.create(
                tournament=tournament,
                team=team,
                player=player,
                status="approved"
            )
            player_idx += 1
    print(f"  ✅ {team.name}: 4 players")

# Also register the test player
try:
    test_player_user = User.objects.get(email='kishanbm25@gmail.com')
    test_player = PlayerProfile.objects.get(user=test_player_user)
    TournamentRegistration.objects.create(
        tournament=tournament,
        team=teams[0],
        player=test_player,
        status="approved"
    )
    print(f"  ✅ kishanbm25 registered to {teams[0].name}")
except:
    pass

print("\n" + "="*80)
print("✅ UPCOMING TOURNAMENT READY FOR TESTING!")
print("="*80)
print(f"""
TOURNAMENT DETAILS:
===================
ID: {tournament.id}
Title: {tournament.title}
Status: {tournament.status}
Teams: 8
Players: 32+

NEXT STEPS FOR BULK SCHEDULE TEST:
===================================

Step 1: Host starts Round 1
  - Go to: http://localhost:3000/tournaments/{tournament.id}/manage
  - Click "Start Round 1"
  - Configure groups (2 groups of 4 teams)
  - Click "Start Round"

Step 2: Host opens Bulk Schedule
  - Look for "Bulk Schedule" button in the round view
  - Click it

Step 3: Host enters schedule data
  - Set date/time/map for groups
  - Save

Step 4: Player checks their dashboard
  - Go to: http://localhost:3000/tournaments/{tournament.id}/dashboard
  - Login as: kishanbm25@gmail.com
  - See the schedule info displayed

READY? Go to Step 1! 🎮
""")
