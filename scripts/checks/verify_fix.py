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

# Get all registrations by this user (as the player)
all_regs = TournamentRegistration.objects.filter(player__user=u)
print(f"\n✅ Registrations for this user (as player): {all_regs.count()}")
for reg in all_regs:
    print(f"  - Tournament: {reg.tournament.title}")
    print(f"    Team ID: {reg.team_id}, Team: {reg.team.name if reg.team else 'NULL'}")

# Get user's team IDs
user_team_ids = list(TeamMember.objects.filter(user=u).values_list('team_id', flat=True))
print(f"\n👥 User's team IDs: {user_team_ids}")

# Check registrations for teams user belongs to
if user_team_ids:
    regs_via_team = TournamentRegistration.objects.filter(team_id__in=user_team_ids)
    print(f"\n✅ Registrations via team membership: {regs_via_team.count()}")
    for reg in regs_via_team:
        print(f"  - Tournament: {reg.tournament.title}, Team: {reg.team.name}")

# Now check what the my-registrations API would return
print("\n" + "="*60)
print("SIMULATING my-registrations API QUERY:")
print("="*60)
from django.db.models import Q

pp = u.player_profile
registrations = TournamentRegistration.objects.filter(
    Q(player=pp) | Q(team_id__in=user_team_ids)
)
print(f"Total visible registrations: {registrations.count()}")
for reg in registrations:
    print(f"  - {reg.tournament.title}")

if registrations.count() > 0:
    print("\n✅ FIX WORKING: Registrations are now visible in my-registrations!")
else:
    print("\n❌ ISSUE: Registrations still not visible")
    print(f"\nDebugging info:")
    print(f"  - Player ID: {pp.id}")
    print(f"  - User's teams: {user_team_ids}")
    
    # Check the actual registration
    if all_regs.exists():
        reg = all_regs.first()
        print(f"\n  Registration details:")
        print(f"    - Tournament ID: {reg.tournament.id}")
        print(f"    - Player ID: {reg.player_id}")
        print(f"    - Team ID: {reg.team_id}")
        
        # Is team_id in user_team_ids?
        if reg.team_id in user_team_ids:
            print(f"    - ✅ Team {reg.team_id} is in user's teams")
        else:
            print(f"    - ❌ Team {reg.team_id} is NOT in user's teams {user_team_ids}")
            print(f"       -> Move user to team {reg.team_id} or update registration")
