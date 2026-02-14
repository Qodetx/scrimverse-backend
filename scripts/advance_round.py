import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService

TID = 21
try:
    t = Tournament.objects.get(id=TID)
except Exception as e:
    print('Tournament not found', e)
    raise SystemExit(1)

print('Tournament', t.id, t.title)
print('current_round:', t.current_round)
print('rounds:', t.rounds)
print('round_status:', t.round_status)
print('selected_teams:', t.selected_teams)

# Ensure selected teams for round 1 exist
sel = t.selected_teams or {}
round1_selected = sel.get('1') or sel.get(1) or []
print('round1 selected count:', len(round1_selected))

# End round 1 and start round 2 logically
round_num = 1
next_round = 2
# Validate enough selected teams
round_config = next((r for r in t.rounds if int(r.get('round')) == round_num), None)
qualifying = int(round_config.get('qualifying_teams') or 0) if round_config else None
print('round_config:', round_config)

if qualifying is None:
    print('Cannot determine qualifying teams from rounds config')
else:
    # If round_config exists, check selected count
    if qualifying > 0:
        if len(round1_selected) != (qualifying * len([g for g in t.registrations.all()])):
            # We can't reliably compute expected count here, just print selected
            print('Selected teams count may not match expected, proceeding anyway')

# Mark round as completed and start next
if not t.round_status:
    t.round_status = {}

t.round_status[str(round_num)] = 'completed'
t.current_round = next_round
if not t.selected_teams:
    t.selected_teams = {}
if str(next_round) not in t.selected_teams:
    t.selected_teams[str(next_round)] = []

 t.save(update_fields=['current_round','round_status','selected_teams'])
print('Updated tournament: current_round', t.current_round)

# Now configure next round using TournamentGroupService
print('Configuring round', next_round)
# For simplicity, call create_5v5_groups with matches_per_group from rounds config
next_config = next((r for r in t.rounds if int(r.get('round')) == next_round), None)
if next_config:
    matches_per_group = next_config.get('matches_per_group') or next_config.get('matches') or 1
    print('matches_per_group for next round:', matches_per_group)
    result = TournamentGroupService.create_5v5_groups(tournament=t, round_number=next_round, matches_per_group=int(matches_per_group))
    print('Result keys:', result.keys())
    print('Num groups created:', len(result.get('groups', [])))
else:
    print('No config for next round, done')
