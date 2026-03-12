import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'scrimverse.settings'
django.setup()

from tournaments.models import Tournament, TournamentRegistration, Match, Group, MatchTeamResult

t = Tournament.objects.get(id=78)
print(f'Tournament: {t.title}')
print(f'Status: {t.status} | Round: {t.current_round}')
print(f'round_status: {t.round_status}')
print()

groups = Group.objects.filter(tournament=t).order_by('round_number', 'id')
for g in groups:
    print(f'Group: {g.name} (ID:{g.id}) | round={g.round_number}')
    matches = Match.objects.filter(group=g).order_by('match_number')
    for m in matches:
        print(f'  Match {m.match_number} (ID:{m.id}) | status={m.status}')
        results = MatchTeamResult.objects.filter(match=m)
        for r in results:
            print(f'    Team: {r.team_name} | pos={r.position} | kills={r.kills} | pts={r.total_points}')

print()
regs = TournamentRegistration.objects.filter(tournament=t, status='confirmed').select_related('team')
print(f'Total confirmed teams: {regs.count()}')
for r in regs:
    print(f'  Reg ID:{r.id} | Team: {r.team.name}')
