#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember
from tournaments.models import TournamentRegistration

# Get the user
try:
    u = User.objects.get(email='kishanbm2300@gmail.com')
    print(f"User found: {u.email}, ID: {u.id}")
except User.DoesNotExist:
    print("User not found!")
    exit(1)

# Check registrations for this user (direct registrations)
regs = TournamentRegistration.objects.filter(player__user=u)
print(f"\n✓ Registrations for this user (direct): {regs.count()}")
for reg in regs:
    print(f"  - Tournament: {reg.tournament.name}, Team ID: {reg.team_id}, Team Name: {reg.team.name if reg.team else 'None'}")

# Check team membership
team_memberships = TeamMember.objects.filter(user=u)
print(f"\n✓ Team memberships: {team_memberships.count()}")
for tm in team_memberships:
    print(f"  - Team: {tm.team.name} (ID: {tm.team.id})")

# Cross-check: registrations for teams user belongs to
user_team_ids = list(team_memberships.values_list('team_id', flat=True))
print(f"\nUser's team IDs: {user_team_ids}")

if user_team_ids:
    regs_via_team = TournamentRegistration.objects.filter(team_id__in=user_team_ids)
    print(f"\n✓ Registrations via team membership: {regs_via_team.count()}")
    for reg in regs_via_team:
        print(f"  - Tournament: {reg.tournament.name}, Team: {reg.team.name if reg.team else 'None'}")
else:
    print("\nNo team memberships found")

print("\n" + "="*60)
print("SUMMARY:")
print("="*60)
total_registrations = regs.count() + (regs_via_team.count() if user_team_ids else 0)
print(f"Total registrations visible via my-registrations endpoint: {total_registrations}")
if total_registrations > 0:
    print("✅ FIX WORKING: Registrations are now visible!")
else:
    print("❌ FIX NOT WORKING: Registrations still not visible")
