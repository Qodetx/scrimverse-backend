#!/usr/bin/env python
import os
import django
import random
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from accounts.models import HostProfile, PlayerProfile, Team, User
from tournaments.models import Tournament, TournamentRegistration, Group, Match

print("\n" + "="*80)
print("🎮 CREATING ADDITIONAL BGMI 4v4 TEST TOURNAMENT")
print("="*80)

# Get or create host
try:
    host_user = User.objects.get(email='kishan@qodet.com')
    host = HostProfile.objects.get(user=host_user)
    print(f"✅ Found host: {host.user.email}")
except:
    print("❌ Host not found")
    exit()

# Create players for Tournament 73 (different players to avoid conflicts)
print("\n" + "="*52)
print("👥 CREATING TEST PLAYERS FOR TOURNAMENT 73")
print("="*52)

players = []
for i in range(73001, 73033):  # 32 players (8 teams × 4 players)
    username = f"player{i}"
    email = f"player{i}@test.com"
    
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email}
    )
    
    player, created = PlayerProfile.objects.get_or_create(
        user=user,
        defaults={'in_game_name': f"IGN_{username}"}
    )
    
    if created:
        print(f"  ✅ Created: {username}")
    else:
        print(f"  ℹ️  Found: {username}")
    
    players.append(player)

# Create tournament
print("\n" + "="*52)
print("🏆 CREATING BGMI TOURNAMENT 73")
print("="*52)

now = timezone.now()
tournament_start = now + timedelta(hours=1)
tournament_end = now + timedelta(hours=6)

tournament = Tournament.objects.create(
    host=host,
    title="BGMI Squad 4v4 Test Tournament 2",
    description="Second BGMI 4v4 tournament for testing modal routing",
    game_name="BGMI",
    game_mode="Squad",
    max_participants=8,
    entry_fee=0.00,
    prize_pool=0.00,
    registration_start=now,
    registration_end=now + timedelta(minutes=30),
    tournament_start=tournament_start,
    tournament_end=tournament_end,
    status="ongoing",
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
print(f"   Rounds: {tournament.rounds}")

# Create teams
print("\n" + "="*52)
print("🎯 CREATING TEAMS")
print("="*52)

teams = []
team_names = [
    "BGMI Team 73-A",
    "BGMI Team 73-B", 
    "BGMI Team 73-C",
    "BGMI Team 73-D",
    "BGMI Team 73-E",
    "BGMI Team 73-F",
    "BGMI Team 73-G",
    "BGMI Team 73-H",
]

for idx, team_name in enumerate(team_names):
    team, created = Team.objects.get_or_create(
        name=team_name,
        defaults={'captain': host_user}
    )
    teams.append(team)
    print(f"  ✅ Team: {team_name}")

# Register teams and players
print("\n" + "="*52)
print("📝 REGISTERING TEAMS & PLAYERS")
print("="*52)

player_idx = 0
for team in teams:
    # Add 4 players to this team
    for j in range(4):
        player = players[player_idx]
        player_reg = TournamentRegistration.objects.create(
            tournament=tournament,
            team=team,
            player=player,
            status="approved"
        )
        player_idx += 1
    
    print(f"  ✅ {team.name}: 4 players registered")

print(f"\n✅ Total registrations: {TournamentRegistration.objects.filter(tournament=tournament).count()}")

# Create groups for Round 1 (8 teams into 2 groups of 4)
print("\n" + "="*52)
print("👥 CREATING GROUPS FOR ROUND 1")
print("="*52)

round_1_groups = [
    {
        "name": "Group A",
        "teams": teams[0:4]
    },
    {
        "name": "Group B", 
        "teams": teams[4:8]
    }
]

for group_data in round_1_groups:
    group = Group.objects.create(
        tournament=tournament,
        round_number=1,
        group_name=group_data["name"],
        qualifying_teams=1
    )
    
    # Add team registrations to group
    for team in group_data["teams"]:
        team_registrations = TournamentRegistration.objects.filter(tournament=tournament, team=team, player__isnull=False)
        group.teams.set(team_registrations)
    
    print(f"  ✅ {group_data['name']}: {group.teams.count()} players")

print("\n" + "="*80)
print("✅ TOURNAMENT 73 SETUP COMPLETE!")
print("="*80)
print(f"""
Tournament Details:
- ID: {tournament.id}
- Title: {tournament.title}
- Game: {tournament.game_name} ({tournament.game_mode})
- Teams: {len(teams)}
- Players: {32}
- Status: {tournament.status}
- Format: Multi-Team (BGMI)
- Will show: EliminatedTeamsModal

Test Instructions:
1. Go to: http://localhost:3000/tournaments/{tournament.id}/manage
2. Click "Advance Round" after configuring matches
3. Verify EliminatedTeamsModal displays (qualified/eliminated teams)
4. Compare with Tournament 72 (Valorant) which shows HeadToHeadResultsModal
""")
