#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament
from tournaments.serializers import TournamentDetailSerializer

tournament = Tournament.objects.get(id=84)
serializer = TournamentDetailSerializer(tournament)

# Check what the serializer returns for registrations
regs_data = serializer.data.get('registrations', [])
print(f'Total registrations in API response: {len(regs_data)}')
print(f'\nFirst 3 registrations:')
for reg in regs_data[:3]:
    print(f'  Team: {reg.get("team")}')

# Count unique teams from API response
unique_teams = set()
for reg in regs_data:
    team = reg.get('team')
    if team:
        unique_teams.add(team)
        
print(f'\nUnique Teams in API: {sorted(unique_teams)}')
print(f'Count: {len(unique_teams)}')
