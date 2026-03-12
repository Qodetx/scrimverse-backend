#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration

t = Tournament.objects.get(id=85)

# Update entry fee to 0
t.entry_fee = 0.00
t.save(update_fields=['entry_fee'])
print(f"Updated entry fee to: {t.entry_fee}")

extra_teams = [
    {'name': 'Storm Breakers',  'players': ['stormcap', 'storms2', 'storms3', 'storms4', 'storms5']},
    {'name': 'Iron Wolves',     'players': ['ironwcap', 'ironw2',  'ironw3',  'ironw4',  'ironw5']},
    {'name': 'Neon Blaze',      'players': ['neonbcap', 'neonb2',  'neonb3',  'neonb4',  'neonb5']},
    {'name': 'Dark Matter',     'players': ['darkmcap', 'darkm2',  'darkm3',  'darkm4',  'darkm5']},
    {'name': 'Viper Strike',    'players': ['viperscap','vipers2', 'vipers3', 'vipers4', 'vipers5']},
    {'name': 'Cyber Wolves',    'players': ['cyberwcap','cyberw2', 'cyberw3', 'cyberw4', 'cyberw5']},
    {'name': 'Apex Predators',  'players': ['apexpcap', 'apexp2',  'apexp3',  'apexp4',  'apexp5']},
    {'name': 'Ghost Protocol',  'players': ['ghostpcap','ghostp2', 'ghostp3', 'ghostp4', 'ghostp5']},
]

for team_data in extra_teams:
    users = []
    for uname in team_data['players']:
        email = uname + '@scrimverse.com'
        try:
            u = User.objects.get(email=email)
        except User.DoesNotExist:
            u = User.objects.create_user(
                username=uname,
                email=email,
                password='Secure@Pass123',
                user_type='player',
                is_email_verified=True,
            )
        try:
            PlayerProfile.objects.get(user=u)
        except PlayerProfile.DoesNotExist:
            PlayerProfile.objects.create(
                user=u,
                in_game_name=uname.upper(),
                game_id='ID' + str(u.id),
                preferred_games=['Valorant'],
            )
        users.append(u)

    captain = users[0]
    desc = team_data['name'] + ' - Elite squad'
    team, _ = Team.objects.get_or_create(
        name=team_data['name'],
        captain=captain,
        defaults={'description': desc},
    )

    for i, u in enumerate(users):
        TeamMember.objects.get_or_create(
            team=team,
            user=u,
            username=u.username,
            defaults={'is_captain': i == 0},
        )

    cap_profile = PlayerProfile.objects.get(user=captain)
    members_snapshot = [{'username': u.username} for u in users]

    reg, created = TournamentRegistration.objects.get_or_create(
        tournament=t,
        player=cap_profile,
        team=team,
        defaults={
            'team_name': team.name,
            'team_members': members_snapshot,
            'status': 'confirmed',
            'payment_status': True,
            'is_team_created': True,
        },
    )
    status = 'Registered' if created else 'Already registered'
    print(f"  {status}: {team.name}  ({len(users)} players)")

# Refresh participant count
total = TournamentRegistration.objects.filter(tournament=t, status='confirmed').count()
t.current_participants = total
t.save(update_fields=['current_participants'])

print()
print(f"Tournament ID   : {t.id}")
print(f"Title           : {t.title}")
print(f"Entry Fee       : {t.entry_fee}")
print(f"Status          : {t.status}")
print(f"Teams Registered: {t.current_participants} / {t.max_participants}")
