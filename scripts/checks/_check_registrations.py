import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','scrimverse.settings')
django.setup()
from tournaments.models import Tournament, TournamentRegistration

t = Tournament.objects.filter(id=12).first()
if not t:
    print('Tournament 12 not found')
else:
    regs = TournamentRegistration.objects.filter(tournament=t)
    print('Tournament:', t.title, 'ID:', t.id)
    print('TournamentRegistration count:', regs.count())
    for r in regs:
        team_name = r.team.name if getattr(r,'team',None) else None
        print('-', 'Reg id', r.id, 'team:', team_name, 'team_members:', r.team_members)
