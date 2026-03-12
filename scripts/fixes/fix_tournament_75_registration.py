#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration
from accounts.models import Team, PlayerProfile, User

print("\n" + "="*80)
print("🔄 FIXING TOURNAMENT 75 REGISTRATION STRUCTURE")
print("="*80)

# Get tournament
try:
    tournament = Tournament.objects.get(id=75)
except Tournament.DoesNotExist:
    print("❌ Tournament 75 not found")
    exit()

# Delete old registrations
print("\n❌ Deleting incorrect player registrations...")
old_count = TournamentRegistration.objects.filter(tournament=tournament).count()
TournamentRegistration.objects.filter(tournament=tournament).delete()
print(f"   Deleted {old_count} registrations")

# Get 8 teams
print("\n" + "="*52)
print("👥 RE-REGISTERING TEAMS WITH PLAYERS")
print("="*52)

teams = Team.objects.filter(name__startswith='BGMI Team 73')
print(f"Found {teams.count()} teams")

# Get all players
all_players = PlayerProfile.objects.filter(user__username__startswith='player73').order_by('id')
print(f"Found {all_players.count()} players")

# Register each team as primary registration
player_index = 0
for team in teams:
    # Register 4 players under this team
    team_players = []
    for j in range(4):
        if player_index < all_players.count():
            player = all_players[player_index]
            player_reg = TournamentRegistration.objects.create(
                tournament=tournament,
                team=team,
                player=player,
                status="approved"
            )
            team_players.append(player.user.username)
            player_index += 1
    
    print(f"✅ {team.name}")
    print(f"   Players: {', '.join(team_players)}")

print("\n" + "="*52)
print("📊 FINAL REGISTRATION STATUS")
print("="*52)

# Count registrations by team
team_registrations = {}
all_regs = TournamentRegistration.objects.filter(tournament=tournament).select_related('team')
for reg in all_regs:
    if reg.team:
        if reg.team.id not in team_registrations:
            team_registrations[reg.team.id] = []
        team_registrations[reg.team.id].append(reg.player.user.username)

team_count = len(team_registrations)
player_count = all_regs.count()

print(f"✅ Teams: {team_count}")
for team_id, players in team_registrations.items():
    team = Team.objects.get(id=team_id)
    print(f"   {team.name}: {len(players)} players")

print(f"✅ Total player registrations: {player_count}")

# Update tournament stats
tournament.current_participants = player_count  # Show total participants (players)
tournament.save(update_fields=['current_participants'])

print("\n" + "="*80)
print("✅ TOURNAMENT 75 REGISTRATION FIXED!")
print("="*80)
print(f"""
Structure:
- Teams: {team_count}
- Players per team: 4
- Total players: {player_count}

Now the RoundConfigModal should show:
- Total Teams: {team_count}
- And display each team with its 4 players
""")
