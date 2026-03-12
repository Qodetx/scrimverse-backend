#!/usr/bin/env python
"""
Script to create a COD tournament with registered teams ready for BO3 testing
"""
import os
import django
from datetime import datetime, timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import HostProfile, PlayerProfile, User, Team
from tournaments.models import Tournament, TournamentRegistration

# Get or create test host
try:
    host = HostProfile.objects.get(id=1)
    print(f"✓ Using host: {host.user.username} (ID: {host.id})")
except HostProfile.DoesNotExist:
    print("❌ Host with ID 1 not found. Please create a host first.")
    exit(1)

# Create test COD tournament
now = timezone.now()
tournament = Tournament.objects.create(
    host=host,
    title='COD BO3 Test Tournament',
    game_name='COD',
    game_mode='5v5',
    description='Test tournament for BO3 (3 maps) with 4 teams forming 2 lobbies',
    max_participants=4,
    entry_fee=0,
    prize_pool=10000,
    registration_start=now - timedelta(days=7),
    registration_end=now + timedelta(days=1),
    tournament_start=now - timedelta(hours=1),  # Started 1 hour ago (ongoing)
    tournament_end=now + timedelta(days=2),
    status='ongoing',  # Already live!
    current_round=0,  # Not started yet, ready to configure
    rules='Standard COD tournament rules. Best of 3 maps.',
    round_status={},
    rounds=[
        {'round': 1, 'max_teams': 4, 'qualifying_teams': 2},
        {'round': 2, 'max_teams': 2, 'qualifying_teams': 1},
    ],
    round_names={'1': 'Semi-Finals', '2': 'Grand Finals'},
    placement_points={'1': 100, '2': 50},
    plan_type='basic',
    plan_price=299.00,
    plan_payment_status=True,
)

print(f"\n✓ Created Tournament: {tournament.title} (ID: {tournament.id})")
print(f"  Status: {tournament.status}")
print(f"  Current Round: {tournament.current_round}")

# Create 4 players and teams
player_data = [
    {'username': 'cod_team1_lead', 'email': 'team1@test.com', 'team_name': 'FrostBite Ops'},
    {'username': 'cod_team2_lead', 'email': 'team2@test.com', 'team_name': 'Shadow Squadron'},
    {'username': 'cod_team3_lead', 'email': 'team3@test.com', 'team_name': 'Tactical Strike'},
    {'username': 'cod_team4_lead', 'email': 'team4@test.com', 'team_name': 'Phantom Elite'},
]

team_regs = []
for i, data in enumerate(player_data, 1):
    # Create or get player
    user, created = User.objects.get_or_create(
        username=data['username'],
        defaults={'email': data['email'], 'user_type': 'player'}
    )
    
    if created:
        user.set_password('test123')
        user.save()
        player = PlayerProfile.objects.create(user=user)
        print(f"✓ Created Player: {user.username}")
    else:
        player = PlayerProfile.objects.get(user=user)
        print(f"✓ Using Player: {user.username}")
    
    # Create team
    team, created = Team.objects.get_or_create(
        name=data['team_name'],
        captain=user,
        defaults={'description': f'{data["team_name"]} - Test Team'}
    )
    
    if created:
        print(f"  ✓ Created Team: {team.name}")
    else:
        print(f"  ✓ Using Team: {team.name}")
    
    # Register team to tournament
    registration, created = TournamentRegistration.objects.get_or_create(
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
        print(f"  ✓ Registered: {team.name} to tournament")
    
    team_regs.append(registration)

print(f"\n✓ Total Registered Teams: {tournament.registrations.filter(status='confirmed').count()}")
print(f"\nTournament ID: {tournament.id}")
print(f"Ready for Round Configuration! Now you can:")
print(f"  1. Go to ManageTournament page (ID: {tournament.id})")
print(f"  2. Configure Round 1 with BO3")
print(f"  3. Start matching teams")
