#!/usr/bin/env python
import os
import django
from datetime import datetime, timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration

print("=" * 80)
print("SETTING UP LIVE TOURNAMENT WITH TEAMS AND PLAYERS")
print("=" * 80)

# Step 1: Create or get host user
print("\n[Step 1] Creating/Getting Host User...")
try:
    host_user = User.objects.get(email='kishan@qodet.com')
    print(f"✓ Found existing host user: {host_user.email}")
except User.DoesNotExist:
    host_user = User.objects.create_user(
        username='kishan_qodet',
        email='kishan@qodet.com',
        password='Secure@Pass123',
        user_type='host',
        is_email_verified=True
    )
    print(f"✓ Created new host user: {host_user.email}")

# Create host profile if it doesn't exist
try:
    host_profile = HostProfile.objects.get(user=host_user)
    print(f"✓ Found existing host profile")
except HostProfile.DoesNotExist:
    host_profile = HostProfile.objects.create(user=host_user)
    print(f"✓ Created new host profile")

# Step 2: Create or get main player user (kishanbm25@gmail.com)
print("\n[Step 2] Creating/Getting Main Player User...")
try:
    main_player_user = User.objects.get(email='kishanbm25@gmail.com')
    print(f"✓ Found existing player user: {main_player_user.email}")
except User.DoesNotExist:
    main_player_user = User.objects.create_user(
        username='kishanbm25',
        email='kishanbm25@gmail.com',
        password='Secure@Pass123',
        user_type='player',
        is_email_verified=True
    )
    print(f"✓ Created new player user: {main_player_user.email}")

# Create player profile if it doesn't exist
try:
    main_player_profile = PlayerProfile.objects.get(user=main_player_user)
    print(f"✓ Found existing player profile")
except PlayerProfile.DoesNotExist:
    main_player_profile = PlayerProfile.objects.create(
        user=main_player_user,
        in_game_name="KishanBM",
        game_id="12345678",
        preferred_games=["Valorant", "COD"]
    )
    print(f"✓ Created new player profile")

# Step 3: Create additional player users for teams
print("\n[Step 3] Creating/Getting Additional Players...")
additional_players = [
    {'email': 'pvpplayer1@example.com', 'username': 'pvpplayer1', 'in_game_name': 'Player1_IGL'},
    {'email': 'pvpplayer2@example.com', 'username': 'pvpplayer2', 'in_game_name': 'Player2_Sentinel'},
    {'email': 'pvpplayer3@example.com', 'username': 'pvpplayer3', 'in_game_name': 'Player3_Duelist'},
    {'email': 'pvpplayer4@example.com', 'username': 'pvpplayer4', 'in_game_name': 'Player4_Initiator'},
    {'email': 'pvpplayer5@example.com', 'username': 'pvpplayer5', 'in_game_name': 'Player5_Controller'},
    {'email': 'pvpplayer6@example.com', 'username': 'pvpplayer6', 'in_game_name': 'Player6_Support'},
    {'email': 'pvpplayer7@example.com', 'username': 'pvpplayer7', 'in_game_name': 'Player7_Flex'},
    {'email': 'pvpplayer8@example.com', 'username': 'pvpplayer8', 'in_game_name': 'Player8_Back'},
]

player_users = [main_player_user]

for player_data in additional_players:
    try:
        player_user = User.objects.get(email=player_data['email'])
        print(f"✓ Found existing player: {player_data['email']}")
    except User.DoesNotExist:
        # Ensure username is unique too
        base_username = player_data['username']
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        player_user = User.objects.create_user(
            username=username,
            email=player_data['email'],
            password='Secure@Pass123',
            user_type='player',
            is_email_verified=True
        )
        print(f"✓ Created new player: {player_data['email']} (username: {username})")
    
    # Create player profile if it doesn't exist
    try:
        player_profile = PlayerProfile.objects.get(user=player_user)
    except PlayerProfile.DoesNotExist:
        player_profile = PlayerProfile.objects.create(
            user=player_user,
            in_game_name=player_data['in_game_name'],
            game_id=f"ID_{player_user.id}",
            preferred_games=["Valorant", "COD"]
        )
    
    player_users.append(player_user)

print(f"✓ Total players available: {len(player_users)}")

# Step 4: Create Teams
print("\n[Step 4] Creating Teams with Players...")
teams_data = [
    {
        'name': 'Phoenix Rising',
        'captain': main_player_user,
        'description': 'Rising from the ashes - Valorant champions in making',
        'players': [main_player_user, player_users[1], player_users[2], player_users[3], player_users[4]]
    },
    {
        'name': 'Shadow Nexus',
        'captain': player_users[5],
        'description': 'Darkness and precision combined',
        'players': [player_users[5], player_users[6], player_users[7], player_users[1], player_users[3]]
    },
]

teams = []
for team_data in teams_data:
    captain = team_data['captain']
    players = team_data['players']
    
    # Create or get team
    team, created = Team.objects.get_or_create(
        name=team_data['name'],
        captain=captain,
        defaults={
            'description': team_data['description'],
            'is_temporary': False,
            'total_matches': 0,
            'wins': 0,
            'losses': 0,
        }
    )
    
    status = "Created" if created else "Found existing"
    print(f"✓ {status} team: {team.name}")
    
    # Add team members
    for player in players:
        member, member_created = TeamMember.objects.get_or_create(
            team=team,
            user=player,
            username=player.username,
            defaults={'is_captain': (player.id == captain.id)}
        )
        status = "Added" if member_created else "Already had"
        print(f"  - {status} {player.username}")
    
    teams.append(team)

# Step 5: Create Tournament
print("\n[Step 5] Creating Live Tournament...")
now = timezone.now()

tournament_data = {
    'host': host_profile,
    'title': 'Valorant Pro Showdown',
    'game_name': 'Valorant',
    'game_mode': '5v5',
    'description': 'An exciting 5v5 Valorant tournament featuring the best teams. Open to all skill levels.',
    'event_mode': 'TOURNAMENT',
    'max_participants': 10,
    'entry_fee': 500.00,
    'prize_pool': 10000.00,
    'registration_start': now - timedelta(days=7),
    'registration_end': now + timedelta(hours=2),
    'tournament_start': now - timedelta(minutes=30),  # Started 30 minutes ago
    'tournament_end': now + timedelta(days=3),
    'status': 'ongoing',  # LIVE!
    'current_round': 1,
    'rules': '''
    1. No cheating, hacking, or exploitation of game mechanics
    2. All games must be played on official servers
    3. Team communication via Discord during matches
    4. 5 minutes before match start, teams must be ready
    5. Screenshot required for proof of gameplay
    6. Respect all players and staff
    ''',
    'plan_type': 'featured',
    'is_featured': True,
    'use_groups_system': True,
    'round_status': {'1': 'ongoing'},
    'rounds': [
        {'round': 1, 'max_teams': 8, 'qualifying_teams': 4},
        {'round': 2, 'max_teams': 4, 'qualifying_teams': 2},
        {'round': 3, 'max_teams': 2, 'qualifying_teams': 1},
    ],
    'placement_points': {
        '1': 20,
        '2': 15,
        '3': 12,
        '4': 10,
        '5': 8,
        '6': 6,
        '7': 4,
        '8': 2,
    }
}

tournament = Tournament.objects.create(**tournament_data)
print(f"✓ Created tournament: {tournament.title}")
print(f"  - ID: {tournament.id}")
print(f"  - Status: {tournament.status}")
print(f"  - Current Round: {tournament.current_round}")
print(f"  - Host: {tournament.host.user.email}")

# Step 6: Create Tournament Registrations
print("\n[Step 6] Creating Tournament Registrations...")
for team in teams:
    # Get team members
    team_members = list(team.members.all().values_list('username', flat=True))
    
    # Create registration for team captain
    registration, created = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        player=PlayerProfile.objects.get(user=team.captain),
        team=team,
        defaults={
            'team_name': team.name,
            'team_members': [{'username': m} for m in team_members],
            'status': 'confirmed',
            'payment_status': True,
            'is_team_created': True,
        }
    )
    
    status = "Created" if created else "Already registered"
    print(f"✓ {status} team {team.name}")
    print(f"  - Captain: {team.captain.email}")
    print(f"  - Members ({len(team_members)}): {', '.join(team_members)}")

# Update current_participants
tournament.current_participants = len(teams)
tournament.save()

print("\n" + "=" * 80)
print("✅ TOURNAMENT SETUP COMPLETE!")
print("=" * 80)
print(f"\n📊 Tournament Summary:")
print(f"   ├─ Tournament ID: {tournament.id}")
print(f"   ├─ Title: {tournament.title}")
print(f"   ├─ Game: {tournament.game_name} ({tournament.game_mode})")
print(f"   ├─ Status: {tournament.status.upper()} ⚡")
print(f"   ├─ Host: {tournament.host.user.email}")
print(f"   ├─ Teams Registered: {tournament.current_participants}")
print(f"   ├─ Prize Pool: ₹{tournament.prize_pool:,.2f}")
print(f"   ├─ Entry Fee: ₹{tournament.entry_fee:.2f}/team")
print(f"   └─ Tournament Window: {tournament.tournament_start} to {tournament.tournament_end}")

print(f"\n🎮 Main Player in Tournament:")
print(f"   ├─ Email: kishanbm25@gmail.com")
print(f"   ├─ Team: Phoenix Rising")
print(f"   ├─ Role: Team Captain")
print(f"   └─ Status: REGISTERED ✓")

print(f"\n🏆 Registered Teams ({len(teams)}):")
for idx, team in enumerate(teams, 1):
    members_count = team.members.count()
    print(f"   {idx}. {team.name}")
    print(f"      ├─ Members: {members_count}")
    print(f"      ├─ Captain: {team.captain.email}")
    print(f"      └─ Registration: CONFIRMED ✓")

print(f"\n🚀 Next Steps:")
print(f"   1. Tournament is LIVE and ongoing")
print(f"   2. Teams can start playing matches")
print(f"   3. Manage tournament at: http://localhost:3000/tournaments/{tournament.id}/manage")
print(f"   4. View brackets at: http://localhost:3000/tournaments/{tournament.id}")

print("\n" + "=" * 80)
