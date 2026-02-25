import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'scrimverse.settings'
django.setup()

from accounts.models import User, PlayerProfile, Team, TeamMember
from tournaments.models import TournamentRegistration

user = User.objects.filter(email='kishanbm25@gmail.com').first()
if not user:
    print('NOT FOUND - kishanbm25@gmail.com')
else:
    print(f'User: {user.username} id={user.id} type={user.user_type}')
    try:
        pp = PlayerProfile.objects.get(user=user)
        print(f'PlayerProfile id={pp.id}')
    except PlayerProfile.DoesNotExist:
        print('No PlayerProfile')
        pp = None

    teams_as_cap = Team.objects.filter(captain=user)
    print(f'Teams as captain: {[(t.name, t.id) for t in teams_as_cap]}')

    memberships = TeamMember.objects.filter(user=user)
    print(f'Team memberships: {[(m.team.name, m.team.id) for m in memberships]}')

    if pp:
        regs = TournamentRegistration.objects.filter(player=pp).select_related('tournament', 'team')
        print(f'\nRegistrations ({regs.count()}):')
        for r in regs:
            print(f'  T{r.tournament.id} {r.tournament.title[:40]} | team={r.team_name} | status={r.status}')
