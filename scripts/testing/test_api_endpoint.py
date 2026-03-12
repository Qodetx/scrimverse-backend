#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from accounts.models import User
from tournaments.views import PlayerTournamentRegistrationsView
from tournaments.models import TournamentRegistration
from django.db.models import Q

# Get the user
u = User.objects.get(email='kishanbm2300@gmail.com')
pp = u.player_profile

print(f"Testing my-registrations endpoint for user: {u.email}\n")

# Simulate what the view does
from accounts.models import TeamMember

team_ids = list(TeamMember.objects.filter(user=u).values_list('team_id', flat=True))
print(f"User's team IDs: {team_ids}")

# This is the query the PlayerTournamentRegistrationsView uses
registrations = TournamentRegistration.objects.filter(
    Q(player=pp) | Q(team_id__in=team_ids)
).distinct()

print(f"\nRegistrations found: {registrations.count()}")
print("=" * 60)

for reg in registrations:
    print(f"Tournament: {reg.tournament.title}")
    print(f"  Game: {reg.tournament.game_name}")
    print(f"  Fee: ${reg.tournament.entry_fee}")
    print(f"  Team: {reg.team.name if reg.team else 'No Team'}")
    print(f"  Status: {reg.status}")
    print()

if registrations.count() > 0:
    print("✅ SUCCESS: Registrations are visible in my-registrations API!")
else:
    print("❌ FAILED: No registrations found")
