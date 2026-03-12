#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember
from tournaments.models import TournamentRegistration
from django.db.models import Q

# Get user
u = User.objects.get(email='kishanbm2300@gmail.com')
pp = u.player_profile

print(f"User: {u.email}")
print(f"Player Profile ID: {pp.id}")
print("=" * 60)

# This is exactly what the PlayerTournamentRegistrationsView does
from django.db.models import Q

team_ids = TeamMember.objects.filter(user=u).values_list('team_id', flat=True)
registrations = TournamentRegistration.objects.filter(
    Q(player=pp) | Q(team_id__in=team_ids)
).distinct()

print(f"\n✅ API Query Results:")
print(f"   Total registrations: {registrations.count()}")
print("\nRegistrations:")

for reg in registrations:
    print(f"\n   Tournament: {reg.tournament.title}")
    print(f"   - Game: {reg.tournament.game_name}")
    print(f"   - Fee: ${reg.tournament.entry_fee}")
    print(f"   - Team: {reg.team.name if reg.team else 'No Team'}")
    print(f"   - Status: {reg.status}")

print("\n" + "=" * 60)
print("📝 FRONTEND TEST INSTRUCTIONS:")
print("=" * 60)
print(f"\n1. Open http://localhost:3000 in your browser")
print(f"2. Login with: kishanbm2300@gmail.com")
print(f"3. Navigate to Player Dashboard")
print(f"4. Scroll to 'Registered Matches' section")
print(f"5. You should see 1 tournament: 'Among Us Social Free'")
print(f"\n✅ If you see the tournament, the fix is WORKING!")
print(f"❌ If you don't see it, there may be a caching issue - refresh the page")
