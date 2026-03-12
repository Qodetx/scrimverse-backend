import os
import django
import sys
# Add project root to PYTHONPATH so 'scrimverse' package can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.contrib.auth import get_user_model
from tournaments.models import TournamentRegistration, Tournament
from accounts.models import Team, PlayerProfile
from django.db import transaction
from django.core.exceptions import ValidationError

User = get_user_model()

TID = 30
TOTAL_TEAMS = 30

try:
    t = Tournament.objects.get(id=TID)
except Tournament.DoesNotExist:
    print('Tournament', TID, 'not found')
    sys.exit(1)

print('Target tournament:', t.id, t.title, 'status=', t.status)

created_teams = 0
created_regs = 0

prefix = 'T30 Team'

existing_nums = []
for tm in Team.objects.filter(**{'name__istartswith': prefix}):
    try:
        n = int(tm.name.split()[-1])
        existing_nums.append(n)
    except:
        pass
start_idx = max(existing_nums) + 1 if existing_nums else 1

original_max = getattr(t, 'max_participants', None)
if original_max is None or original_max < TOTAL_TEAMS:
    t.max_participants = max(TOTAL_TEAMS, original_max or 0)
    t.save()

with transaction.atomic():
    for i in range(TOTAL_TEAMS):
        n = start_idx + i
        team_name = f'{prefix} {n}'
        members = []
        for j in range(5):
            uname = f't30_p{n}_{j+1}'
            user, _ = User.objects.get_or_create(username=uname, defaults={'email': f'{uname}@test.com'})
            PlayerProfile.objects.get_or_create(user=user)
            members.append(user)
        team_qs = Team.objects.filter(name=team_name)
        if team_qs.exists():
            team = team_qs.first()
            if not team.captain:
                team.captain = members[0]
                team.save(update_fields=['captain'])
        else:
            team = Team.objects.create(name=team_name, captain=members[0], is_temporary=False)
            created_teams += 1
        if not TournamentRegistration.objects.filter(tournament=t, team=team).exists():
            try:
                TournamentRegistration.objects.create(
                    tournament=t,
                    player=PlayerProfile.objects.get(user=members[0]),
                    team=team,
                    status='confirmed',
                    team_name=team.name,
                    team_members=[u.username for u in members],
                )
                created_regs += 1
            except ValidationError:
                TournamentRegistration.objects.create(
                    tournament=t,
                    player=PlayerProfile.objects.get(user=members[0]),
                    team=team,
                    status='pending',
                    team_name=team.name,
                    team_members=[u.username for u in members],
                )
                created_regs += 1

regs_count = TournamentRegistration.objects.filter(tournament=t).count()
t.current_participants = regs_count
if getattr(t, 'max_participants', 0) < regs_count:
    t.max_participants = regs_count
t.save()

print(f'Created teams={created_teams}, created_regs={created_regs}, total_regs={regs_count}')
print('Sample team names:', [f'{prefix} {start_idx + i}' for i in range(min(5, TOTAL_TEAMS))])
