#!/usr/bin/env python
"""
Configure Round 1 as BO3 for tournament ID 64 using TournamentGroupService
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scrimverse.settings')
django.setup()

from tournaments.models import Tournament
from tournaments.services import TournamentGroupService

TOURNAMENT_ID = 64
ROUND_NUMBER = 1
MATCHES_PER_GROUP = 3  # BO3

try:
    t = Tournament.objects.get(id=TOURNAMENT_ID)
    print(f"Found tournament: {t.title} (ID: {t.id})")
except Tournament.DoesNotExist:
    print(f"Tournament {TOURNAMENT_ID} not found")
    raise SystemExit(1)

result = TournamentGroupService.create_5v5_groups(tournament=t, round_number=ROUND_NUMBER, matches_per_group=MATCHES_PER_GROUP)

if 'error' in result:
    print('Error creating groups:', result['error'])
    raise SystemExit(1)

print('\nCreated groups:')
for g in result['groups']:
    print(f"  - {g.group_name} (ID: {g.id}) | Teams: {[r.team_name for r in g.teams.all()]} | Matches: {g.matches.count()}")

if result.get('bye_team'):
    print('\nBye team:', result['bye_team'].team_name)

print('\nTotal lobbies created:', result.get('total_lobbies'))
