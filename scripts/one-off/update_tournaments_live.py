#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament
from django.utils import timezone
from datetime import timedelta

tournaments = Tournament.objects.filter(id__in=[88, 89, 90])
now = timezone.now()

for tournament in tournaments:
    tournament.status = 'ongoing'
    tournament.tournament_start = now - timedelta(minutes=5)
    tournament.tournament_end = now + timedelta(hours=5)
    team_count = tournament.registrations.values('team').distinct().count()
    tournament.current_participants = team_count
    tournament.save()
    print(f'OK: T{tournament.id} {tournament.game_name} - {team_count} teams')

print('\nAll tournaments updated successfully!')
