import os
import sys
from math import ceil

# Setup Django
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()

from tournaments.models import Tournament, TournamentRegistration

TID = 30
try:
    t = Tournament.objects.get(id=TID)
except Tournament.DoesNotExist:
    print('Tournament', TID, 'not found')
    sys.exit(1)

confirmed = TournamentRegistration.objects.filter(tournament=t, status='confirmed').count()
print('Confirmed teams:', confirmed)

rounds = []
round_num = 1
teams = confirmed
while teams > 1:
    qualifying = ceil(teams / 2)
    rounds.append({'round': round_num, 'max_teams': teams, 'qualifying_teams': qualifying})
    teams = qualifying
    round_num += 1

if not rounds:
    rounds = [{'round': 1, 'max_teams': max(1, confirmed), 'qualifying_teams': 0}]

round_status = {str(r['round']): 'upcoming' for r in rounds}
round_names = {str(r['round']): f'Round {r["round"]}' for r in rounds}

print('Generated rounds:', rounds)

# Save to tournament
t.rounds = rounds
t.round_status = round_status
t.round_names = round_names
t.current_round = 0
t.save()

print('Saved rounds to Tournament', t.id)
