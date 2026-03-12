import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()
from tournaments.models import Tournament, Group

TID = 21
try:
    t = Tournament.objects.get(id=TID)
except Exception as e:
    print('Tournament not found', e)
    raise SystemExit(1)

print('Tournament', t.id, t.title)
round_num = 1
groups = Group.objects.filter(tournament=t, round_number=round_num).order_by('id')
print('Found groups:', groups.count())
winners = []
for g in groups:
    # If group status not completed but all matches are completed, mark completed
    try:
        if g.is_completed() and g.status != 'completed':
            g.status = 'completed'
            g.save()
            print(f'Updated group {g.group_name} status -> completed')
    except Exception as e:
        print('Error checking completion for group', g.id, e)

    if not g.winner:
        w = g.determine_group_winner()
        if w:
            print(f'Group {g.group_name} winner set to reg id {w.id}')
            winners.append(w.id)
        else:
            print(f'Group {g.group_name} has no winner determined')
    else:
        print(f'Group {g.group_name} already has winner reg id {g.winner.id}')
        winners.append(g.winner.id)

print('Total winners found:', len(winners))
if winners:
    t.selected_teams = t.selected_teams or {}
    t.selected_teams[str(round_num)] = winners
    t.save(update_fields=['selected_teams'])
    print('Tournament.selected_teams updated for round', round_num)
else:
    print('No winners to set; cannot populate selected_teams')

print('Done')
