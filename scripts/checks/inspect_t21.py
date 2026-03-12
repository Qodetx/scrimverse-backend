import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()
from tournaments.models import Tournament, Group, Match, TournamentRegistration

TID = 21
try:
    t = Tournament.objects.get(id=TID)
except Exception as e:
    print('Tournament not found', e)
    raise SystemExit(1)

print('Tournament id:', t.id, 'title:', t.title)
print('current_round =', t.current_round)
print('round_status =', t.round_status)
print('selected_teams =', t.selected_teams)
print('rounds =', t.rounds)
print('confirmed_regs =', TournamentRegistration.objects.filter(tournament=t, status="confirmed").count())
print('groups_r1 =', Group.objects.filter(tournament=t, round_number=1).count())
print('groups_r1_completed =', Group.objects.filter(tournament=t, round_number=1, status='completed').count())
print('groups_r2 =', Group.objects.filter(tournament=t, round_number=2).count())
print('matches_total =', Match.objects.filter(group__tournament=t).count())
print('matches_completed =', Match.objects.filter(group__tournament=t, status='completed').count())

# Show selected_teams detail
sel = t.selected_teams or {}
for k, v in sel.items():
    print(f'selected_teams round {k}: count={len(v) if v else 0} -> {v}')

# For each group in round 1, show matches and scores existence
for g in Group.objects.filter(tournament=t, round_number=1).order_by('id'):
    m = g.matches.all()
    completed = m.filter(status='completed').count()
    print(f'Group {g.group_name} (id={g.id}): matches={m.count()}, completed={completed}')
    for match in m:
        print(f'  Match {match.id} num={match.match_number} status={match.status} scores={match.scores.exists()}')
