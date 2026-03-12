#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember, Team
from tournaments.models import TournamentRegistration

# Get the user
u = User.objects.get(email='kishanbm2300@gmail.com')

# Get the registration
reg = TournamentRegistration.objects.filter(player__user=u).first()
print(f"📋 Registration Analysis:")
print(f"  Tournament: {reg.tournament.title}")
print(f"  Registration Team: {reg.team.name} (ID: {reg.team_id})")
print(f"  Team Members: {', '.join([m.user.email for m in TeamMember.objects.filter(team=reg.team)])}")

# Get user's teams
user_teams = TeamMember.objects.filter(user=u)
print(f"\n👥 User's Teams:")
for tm in user_teams:
    members = TeamMember.objects.filter(team=tm.team)
    member_emails = ', '.join([m.user.email for m in members])
    print(f"  Team: {tm.team.name} (ID: {tm.team.id})")
    print(f"    Members: {member_emails}")

# Check if user is in the registration team
if reg.team_id in [tm.team_id for tm in user_teams]:
    print(f"\n✅ User IS in the registration team")
else:
    print(f"\n❌ User is NOT in the registration team")
    print(f"\n🔧 Quick fix: Update registration to use team {user_teams.first().team.name}")
    
    # Option to fix
    print("\nWould you like to:")
    print("1. Move user to the registration team (62)?")
    print("2. Update registration to use user's team (60)?")
    print("\nFor now, let's ADD user to team 62 to match the registration:")
    
    # Add user to registration team if not already there
    existing = TeamMember.objects.filter(user=u, team=reg.team).exists()
    if not existing:
        tm = TeamMember.objects.create(user=u, team=reg.team, is_captain=False)
        print(f"✅ Added {u.email} to team {reg.team.name}")
    
    # Verify
    print(f"\n✅ Verification:")
    user_team_ids_updated = list(TeamMember.objects.filter(user=u).values_list('team_id', flat=True))
    print(f"   User's team IDs: {user_team_ids_updated}")
    
    regs_via_team = TournamentRegistration.objects.filter(team_id__in=user_team_ids_updated)
    print(f"   Registrations via team membership: {regs_via_team.count()}")
    for r in regs_via_team:
        print(f"     - {r.tournament.title}")
