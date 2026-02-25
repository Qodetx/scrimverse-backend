#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import TournamentRegistration

# Check registrations for tournament 84
regs = TournamentRegistration.objects.filter(tournament_id=84)
print(f'Total registrations: {regs.count()}')
print(f'\nFirst 5 registrations:')
for reg in regs[:5]:
    print(f'  Player: {reg.player.user.email if reg.player else "None"} | Team ID: {reg.team}')

# Count unique teams
unique_teams = set()
for reg in regs:
    if reg.team:
        unique_teams.add(reg.team)
        
print(f'\nUnique Team IDs: {unique_teams}')
print(f'Unique Team Count: {len(unique_teams)}')
