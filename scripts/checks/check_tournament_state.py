#!/usr/bin/env python
"""Check tournament 64 state: current_participants, confirmed registrations, round_status, registered teams list"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration

TID = 64

t = Tournament.objects.get(id=TID)
confirmed = TournamentRegistration.objects.filter(tournament=t, status='confirmed')
print(f"Tournament: {t.title} (ID: {t.id})")
print(f"max_participants: {t.max_participants}")
print(f"current_participants (stored): {t.current_participants}")
print(f"confirmed registrations (query): {confirmed.count()}")
print('Round status:', t.round_status)
print('Rounds:', t.rounds)
print('\nRegistered teams:')
for r in confirmed:
    print(f" - id:{r.id} team_name:{r.team_name} player:{r.player.user.username} team_id:{r.team.id if r.team else 'None'} registered_at:{r.registered_at}")

# Show whether any groups exist for round 1
from tournaments.models import Group, Match
groups = Group.objects.filter(tournament=t, round_number=1)
print(f"\nExisting groups for round 1: {groups.count()}")
for g in groups:
    print(f" - Group: {g.group_name} id:{g.id} teams:{[tm.team_name for tm in g.teams.all()]} matches:{g.matches.count()}")
