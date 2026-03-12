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

from tournaments.models import Tournament, TournamentRegistration, Group

t = Tournament.objects.get(id=30)

# Get current selected teams for Round 1 (the winners)
r1_winners = t.selected_teams.get('1', [])
print('Current R1 winners:', len(r1_winners))

# Get the bye team (T30 Team 31, reg_id=120)
try:
    bye_team = TournamentRegistration.objects.get(id=120)
    print('Bye team found:', bye_team.team_name)
except TournamentRegistration.DoesNotExist:
    print('Bye team ID 120 not found')
    bye_team = None

# Check if bye team already in selected_teams
if bye_team and bye_team.id not in r1_winners:
    r1_winners.append(bye_team.id)
    t.selected_teams['1'] = r1_winners
    print('Added bye team to selected_teams["1"]')
else:
    print('Bye team already in selected_teams or not found')

# Also update round_status to include bye_team_id
if not isinstance(t.round_status.get('1'), dict):
    t.round_status['1'] = {}
t.round_status['1']['bye_team_id'] = 120
t.round_status['1']['status'] = 'completed'

# Delete any Round 2 groups that were created with incomplete data
r2_groups = Group.objects.filter(tournament=t, round_number=2)
if r2_groups.exists():
    count = r2_groups.count()
    r2_groups.delete()
    print(f'Deleted {count} Round 2 groups (stale)')

t.save()
print('Updated tournament state')
print('Selected teams R1:', len(t.selected_teams.get('1', [])))
print('Round status R1:', t.round_status.get('1'))
