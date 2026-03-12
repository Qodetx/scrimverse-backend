#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember
from tournaments.models import TournamentRegistration

# Get the user
u = User.objects.get(email='kishanbm2300@gmail.com')
print(f"User: {u.email}, ID: {u.id}")

# Get all registrations by this user (as the player who registered)
all_regs = TournamentRegistration.objects.filter(player__user=u)
print(f"\nAll registrations for user (as player): {all_regs.count()}")
for reg in all_regs:
    print(f"  ID: {reg.id}")
    print(f"    Tournament: {reg.tournament.name}")
    print(f"    Current team_id: {reg.team_id}")
    print(f"    Team name field: {reg.team_name}")
    print()

# Get user's teams
user_teams = TeamMember.objects.filter(user=u).values_list('team_id', flat=True)
print(f"User's team IDs: {list(user_teams)}")

# If there are registrations and teams, update the registrations to link to the user's team
if all_regs.exists() and user_teams:
    team_id = user_teams[0]  # Get first team
    print(f"\n🔧 Updating {all_regs.count()} registration(s) to link to team {team_id}...")
    
    for reg in all_regs:
        if reg.team_id is None:
            reg.team_id = team_id
            reg.save()
            print(f"  ✅ Updated registration {reg.id}")
    
    # Re-verify
    print("\n✅ Verification after update:")
    regs_via_team = TournamentRegistration.objects.filter(team_id=team_id)
    print(f"   Registrations for team {team_id}: {regs_via_team.count()}")
    for reg in regs_via_team:
        print(f"     - {reg.tournament.name}")
else:
    print("\n⚠️  No registrations or teams found to update")
    print("   You need to create a new tournament registration first")
