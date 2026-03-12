#!/usr/bin/env python
import os
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, TeamMember
from tournaments.models import Tournament, TournamentRegistration, Team

# Get tournament ID 8
try:
    tournament = Tournament.objects.get(id=8)
    print(f"Found tournament: {tournament.title} (ID: {tournament.id})")
except Tournament.DoesNotExist:
    print("Tournament ID 8 not found!")
    exit(1)

# Get or create players
print("\n📝 Creating/Finding players...")

players_data = [
    {'email': 'kishanbm25@gmail.com', 'username': 'kishanbm25', 'phone': '9876543210'},
    {'email': 'player2@test.com', 'username': 'player2', 'phone': '9876543211'},
    {'email': 'player3@test.com', 'username': 'player3', 'phone': '9876543212'},
    {'email': 'player4@test.com', 'username': 'player4', 'phone': '9876543213'},
    {'email': 'player5@test.com', 'username': 'player5', 'phone': '9876543214'},
    {'email': 'player6@test.com', 'username': 'player6', 'phone': '9876543215'},
    {'email': 'player7@test.com', 'username': 'player7', 'phone': '9876543216'},
    {'email': 'player8@test.com', 'username': 'player8', 'phone': '9876543217'},
    {'email': 'player9@test.com', 'username': 'player9', 'phone': '9876543218'},
    {'email': 'player10@test.com', 'username': 'player10', 'phone': '9876543219'},
    {'email': 'player11@test.com', 'username': 'player11', 'phone': '9876543220'},
    {'email': 'player12@test.com', 'username': 'player12', 'phone': '9876543221'},
    {'email': 'player13@test.com', 'username': 'player13', 'phone': '9876543222'},
    {'email': 'player14@test.com', 'username': 'player14', 'phone': '9876543223'},
    {'email': 'player15@test.com', 'username': 'player15', 'phone': '9876543224'},
    {'email': 'player16@test.com', 'username': 'player16', 'phone': '9876543225'},
    {'email': 'player17@test.com', 'username': 'player17', 'phone': '9876543226'},
    {'email': 'player18@test.com', 'username': 'player18', 'phone': '9876543227'},
    {'email': 'player19@test.com', 'username': 'player19', 'phone': '9876543228'},
    {'email': 'player20@test.com', 'username': 'player20', 'phone': '9876543229'},
]

players = []
for data in players_data:
    # Try to find by email first, then by username
    user = User.objects.filter(email=data['email']).first()
    if not user:
        user = User.objects.filter(username=data['username']).first()
    if not user:
        user = User.objects.create(
            email=data['email'],
            username=data['username'],
            user_type='player',
            phone_number=data['phone'],
            is_email_verified=True
        )
        user.set_password('testpass123')
        user.save()
        print(f"  ✅ Created user: {user.username}")
    else:
        print(f"  ℹ️  Found user: {user.username} ({user.email})")
    
    # Ensure PlayerProfile exists
    profile, _ = PlayerProfile.objects.get_or_create(user=user)
    players.append({'user': user, 'profile': profile})

print(f"\n✅ Total players ready: {len(players)}")

# Create teams with registrations for tournament
print(f"\n🎮 Creating teams and registrations for {tournament.title}...")

required_players = 5  # 5v5 tournament

teams_created = 0
for i in range(4):  # Create 4 teams (20 players total, 5 per team)
    team_name = f"Test Team {chr(65 + i)}"  # Test Team A, B, C, D
    
    # Create team
    team, created = Team.objects.get_or_create(
        name=team_name,
        defaults={
            'captain': players[i * required_players]['user'] if i * required_players < len(players) else players[0]['user'],
            'is_temporary': False,
        }
    )
    
    if created:
        print(f"  ✅ Created team: {team_name}")
    else:
        print(f"  ℹ️  Found team: {team_name}")
    
    # Add players to team
    team_members = []
    team_member_usernames = []
    for j in range(required_players):
        player_idx = (i * required_players + j) % len(players)
        player = players[player_idx]
        
        member, created = TeamMember.objects.get_or_create(
            team=team,
            user=player['user'],
            defaults={
                'username': player['user'].username,
                'is_captain': (j == 0)
            }
        )
        team_members.append(player['user'].username)
        team_member_usernames.append(player['user'].username)
        
        if created:
            print(f"    └─ Added {player['user'].username} to {team_name}")
    
    # Create tournament registration for this team
    captain_idx = i * required_players if i * required_players < len(players) else 0
    captain_profile = players[captain_idx]['profile']
    
    registration, created = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        team=team,
        defaults={
            'player': captain_profile,
            'team_name': team_name,
            'team_members': team_member_usernames,
            'status': 'confirmed',
            'payment_status': True,
        }
    )
    
    if created:
        print(f"  ✅ Registered team '{team_name}' to tournament (ID: {tournament.id})")
        print(f"     Members: {', '.join(team_members)}")
        teams_created += 1
    else:
        print(f"  ℹ️  Team '{team_name}' already registered")

print(f"\n🎯 Summary:")
print(f"  Tournament: {tournament.title} (ID: {tournament.id})")
print(f"  Teams registered: {teams_created}")
print(f"  Players per team: {required_players}")
print(f"  Player with kishanbm25@gmail.com is in first team ✅")
print(f"\n✨ Now the tournament has registered teams!")
print(f"   Go to ManageTournament → Click 'INITIALIZE MATCHES' to create groups and matches.")

