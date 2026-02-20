#!/usr/bin/env python
"""
Add additional COD teams to an existing tournament and update participant count
"""
import os
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, Team
from tournaments.models import Tournament, TournamentRegistration

TOURNAMENT_ID = 64

try:
    tournament = Tournament.objects.get(id=TOURNAMENT_ID)
    print(f"Found tournament: {tournament.title} (ID: {tournament.id})")
except Tournament.DoesNotExist:
    print(f"Tournament with ID {TOURNAMENT_ID} not found")
    exit(1)

new_teams = [
    {'username': 'cod_team5_lead', 'email': 'team5@test.com', 'team_name': 'Rogue Unit'},
    {'username': 'cod_team6_lead', 'email': 'team6@test.com', 'team_name': 'Night Hawks'},
    {'username': 'cod_team7_lead', 'email': 'team7@test.com', 'team_name': 'Apex Predators'},
]

for data in new_teams:
    user, created = User.objects.get_or_create(
        username=data['username'],
        defaults={'email': data['email'], 'user_type': 'player'}
    )
    if created:
        user.set_password('test123')
        user.save()
        player = PlayerProfile.objects.create(user=user)
        print(f"Created player: {user.username}")
    else:
        player = PlayerProfile.objects.get(user=user)
        print(f"Using player: {user.username}")

    team, created = Team.objects.get_or_create(
        name=data['team_name'],
        defaults={'captain': user, 'description': f'{data["team_name"]} - Test Team'}
    )
    if created:
        print(f"Created team: {team.name}")
    else:
        print(f"Using team: {team.name}")

    reg, created = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        player=player,
        defaults={
            'team': team,
            'team_name': team.name,
            'status': 'confirmed',
            'payment_status': True,
        }
    )
    if created:
        print(f"Registered team {team.name} to tournament")
    else:
        # Ensure it's confirmed
        if reg.status != 'confirmed':
            reg.status = 'confirmed'
            reg.payment_status = True
            reg.save()
            print(f"Updated registration status to confirmed for {team.name}")
        else:
            print(f"Registration already exists and confirmed for {team.name}")

# Update current_participants count
confirmed_count = tournament.registrations.filter(status='confirmed').count()
tournament.current_participants = confirmed_count
# Also update rounds metadata if needed (not modifying rounds here)
tournament.save(update_fields=['current_participants'])

print(f"\nUpdated tournament.current_participants to {tournament.current_participants}")
print(f"Total confirmed registrations: {confirmed_count}")
