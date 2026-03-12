#!/usr/bin/env python
"""
Ensure tournament.max_participants >= current confirmed registrations for a tournament
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scrimverse.settings')
django.setup()
from tournaments.models import Tournament, TournamentRegistration
TOURNAMENT_ID = 64
try:
    t = Tournament.objects.get(id=TOURNAMENT_ID)
except Tournament.DoesNotExist:
    print('Tournament not found')
    exit(1)
confirmed = TournamentRegistration.objects.filter(tournament=t, status='confirmed').count()
if t.max_participants < confirmed:
    print(f'Updating tournament.max_participants from {t.max_participants} to {confirmed}')
    t.max_participants = confirmed
    t.save(update_fields=['max_participants'])
else:
    print('No update needed')
print('Current max_participants:', t.max_participants)
print('Confirmed registrations:', confirmed)
