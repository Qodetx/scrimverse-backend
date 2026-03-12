#!/usr/bin/env python
import os
import django
from django.utils import timezone
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, HostProfile, TeamMember
from tournaments.models import Tournament, TournamentRegistration, Team

# ============================================================================
# 1. GET OR CREATE HOST (kishan@qodet.com)
# ============================================================================
print("=" * 80)
print("🔑 SETTING UP HOST")
print("=" * 80)

try:
    host_user = User.objects.get(email='kishan@qodet.com')
    print(f"✅ Found host user: {host_user.email}")
except User.DoesNotExist:
    print("❌ Host user kishan@qodet.com not found!")
    print("   Creating it now...")
    host_user = User.objects.create(
        email='kishan@qodet.com',
        username='kishan_host',
        user_type='host',
        is_email_verified=True
    )
    host_user.set_password('testpass123')
    host_user.save()
    print(f"✅ Created host user: {host_user.email}")

# Ensure HostProfile exists
host_profile, _ = HostProfile.objects.get_or_create(user=host_user)
print(f"✅ Host profile ready: {host_profile.user.email}")

# ============================================================================
# 2. CREATE TEST PLAYERS
# ============================================================================
print("\n" + "=" * 80)
print("👥 CREATING TEST PLAYERS")
print("=" * 80)

# BGMI needs 8 teams × 4 players = 32 players
# Valorant needs 8 teams × 5 players = 40 players
# Total: 72 unique players
players = []
for i in range(1, 81):
    email = f'player{i:02d}@test.com'
    username = f'player{i:02d}'
    
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': username,
            'user_type': 'player',
            'phone_number': f'987654{3200+i:04d}',
            'is_email_verified': True
        }
    )
    
    if created:
        user.set_password('testpass123')
        user.save()
        print(f"  ✅ Created: {username}")
    else:
        print(f"  ℹ️  Found: {username}")
    
    # Ensure PlayerProfile exists
    profile, _ = PlayerProfile.objects.get_or_create(user=user)
    players.append({'user': user, 'profile': profile, 'username': username})

print(f"\n✅ Total players created/found: {len(players)}")

# ============================================================================
# 3. CREATE BGMI SQUAD 4v4 TOURNAMENT
# ============================================================================
print("\n" + "=" * 80)
print("🎮 CREATING BGMI SQUAD 4v4 TOURNAMENT")
print("=" * 80)

now = timezone.now()
bgmi_tournament, created = Tournament.objects.get_or_create(
    title='BGMI Squad Test Tournament 4v4',
    host=host_profile,
    defaults={
        'description': 'BGMI Squad 4v4 Battle Royale test tournament',
        'game_name': 'BGMI',
        'game_mode': 'Squad',
        'max_participants': 8,
        'current_participants': 0,
        'entry_fee': 100.00,
        'prize_pool': 50000.00,
        'tournament_date': (now + timedelta(days=1)).date(),
        'tournament_time': now.time(),
        'registration_start': now,
        'registration_end': now + timedelta(hours=1),
        'tournament_start': now + timedelta(hours=2),
        'tournament_end': now + timedelta(hours=6),
        'use_groups_system': True,
        'event_mode': 'TOURNAMENT',
        'rounds': [
            {'round': 1, 'max_teams': 8, 'qualifying_teams': 4},
            {'round': 2, 'max_teams': 4, 'qualifying_teams': 2},
            {'round': 3, 'max_teams': 2, 'qualifying_teams': 1}
        ],
        'round_names': {'1': 'Qualifiers', '2': 'Semi Finals', '3': 'Grand Finals'},
        'status': 'upcoming'
    }
)

if created:
    print(f"✅ Created BGMI tournament: {bgmi_tournament.title} (ID: {bgmi_tournament.id})")
else:
    print(f"ℹ️  Found BGMI tournament: {bgmi_tournament.title} (ID: {bgmi_tournament.id})")

# Create 8 BGMI teams with 4 players each
print(f"\n📋 Creating BGMI teams (8 teams × 4 players)...")
bgmi_teams = []
bgmi_player_idx = 0

for team_num in range(1, 9):
    team_name = f'BGMI Team {team_num}'
    
    # Create team
    team, created = Team.objects.get_or_create(
        name=team_name,
        defaults={
            'captain': players[bgmi_player_idx]['user'],
            'is_temporary': True,
        }
    )
    
    if created:
        print(f"  ✅ Created: {team_name}")
    else:
        print(f"  ℹ️  Found: {team_name}")
    
    team_members_list = []
    
    # Add 4 players to this team
    for member_num in range(4):
        player = players[bgmi_player_idx]
        
        member, _ = TeamMember.objects.get_or_create(
            team=team,
            user=player['user'],
            defaults={
                'username': player['username'],
                'is_captain': (member_num == 0)
            }
        )
        
        team_members_list.append(player['username'])
        bgmi_player_idx += 1
        
        if _ :
            print(f"      └─ Added: {player['username']}")
    
    # Create tournament registration
    captain = team.captain
    captain_profile = captain.player_profile
    
    registration, created = TournamentRegistration.objects.get_or_create(
        tournament=bgmi_tournament,
        team=team,
        defaults={
            'player': captain_profile,
            'team_name': team_name,
            'team_members': team_members_list,
            'status': 'confirmed',
            'payment_status': True,
        }
    )
    
    if created:
        print(f"    ✅ Registered: {team_name}")
        bgmi_teams.append(team)
    else:
        bgmi_teams.append(team)

bgmi_tournament.current_participants = len(bgmi_teams)
bgmi_tournament.save()

print(f"\n✅ BGMI Tournament Setup Complete!")
print(f"   Tournament ID: {bgmi_tournament.id}")
print(f"   Teams registered: {bgmi_tournament.current_participants}/8")
print(f"   Round structure: Qualifiers (8→4) → Semi-Finals (4→2) → Grand Finals (2→1)")

# ============================================================================
# 4. CREATE VALORANT 5v5 TOURNAMENT
# ============================================================================
print("\n" + "=" * 80)
print("🎮 CREATING VALORANT 5v5 TOURNAMENT")
print("=" * 80)

valorant_tournament, created = Tournament.objects.get_or_create(
    title='Valorant 5v5 Test Tournament',
    host=host_profile,
    defaults={
        'description': 'Valorant 5v5 competitive test tournament',
        'game_name': 'Valorant',
        'game_mode': '5v5',
        'max_participants': 8,
        'current_participants': 0,
        'entry_fee': 200.00,
        'prize_pool': 100000.00,
        'tournament_date': (now + timedelta(days=2)).date(),
        'tournament_time': now.time(),
        'registration_start': now,
        'registration_end': now + timedelta(hours=1),
        'tournament_start': now + timedelta(hours=2),
        'tournament_end': now + timedelta(hours=8),
        'use_groups_system': True,
        'event_mode': 'TOURNAMENT',
        'rounds': [
            {'round': 1, 'max_teams': 8, 'qualifying_teams': 4},
            {'round': 2, 'max_teams': 4, 'qualifying_teams': 2},
            {'round': 3, 'max_teams': 2, 'qualifying_teams': 1}
        ],
        'round_names': {'1': 'Group Stage', '2': 'Semi-Finals', '3': 'Grand Finals'},
        'status': 'upcoming'
    }
)

if created:
    print(f"✅ Created Valorant tournament: {valorant_tournament.title} (ID: {valorant_tournament.id})")
else:
    print(f"ℹ️  Found Valorant tournament: {valorant_tournament.title} (ID: {valorant_tournament.id})")

# Create 8 Valorant teams with 5 players each
print(f"\n📋 Creating Valorant teams (8 teams × 5 players)...")
valorant_teams = []

for team_num in range(1, 9):
    team_name = f'Valorant Team {team_num}'
    
    # Create team
    team, created = Team.objects.get_or_create(
        name=team_name,
        defaults={
            'captain': players[bgmi_player_idx]['user'],
            'is_temporary': True,
        }
    )
    
    if created:
        print(f"  ✅ Created: {team_name}")
    else:
        print(f"  ℹ️  Found: {team_name}")
    
    team_members_list = []
    
    # Add 5 players to this team
    for member_num in range(5):
        player = players[bgmi_player_idx]
        
        member, _ = TeamMember.objects.get_or_create(
            team=team,
            user=player['user'],
            defaults={
                'username': player['username'],
                'is_captain': (member_num == 0)
            }
        )
        
        team_members_list.append(player['username'])
        bgmi_player_idx += 1
        
        if _ :
            print(f"      └─ Added: {player['username']}")
    
    # Create tournament registration
    captain = team.captain
    captain_profile = captain.player_profile
    
    registration, created = TournamentRegistration.objects.get_or_create(
        tournament=valorant_tournament,
        team=team,
        defaults={
            'player': captain_profile,
            'team_name': team_name,
            'team_members': team_members_list,
            'status': 'confirmed',
            'payment_status': True,
        }
    )
    
    if created:
        print(f"    ✅ Registered: {team_name}")
        valorant_teams.append(team)
    else:
        valorant_teams.append(team)

valorant_tournament.current_participants = len(valorant_teams)
valorant_tournament.save()

print(f"\n✅ Valorant Tournament Setup Complete!")
print(f"   Tournament ID: {valorant_tournament.id}")
print(f"   Teams registered: {valorant_tournament.current_participants}/8")
print(f"   Round structure: Group Stage (8→4) → Semi-Finals (4→2) → Grand Finals (2→1)")

# ============================================================================
# 5. FINAL SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("✨ TEST DATA INSERTION COMPLETE!")
print("=" * 80)
print(f"\n🔐 Host: kishan@qodet.com")
print(f"\n📊 Tournament 1 - BGMI Squad 4v4 (Battle Royale)")
print(f"   ID: {bgmi_tournament.id}")
print(f"   Teams: {bgmi_tournament.current_participants}")
print(f"   Players per team: 4")
print(f"   Format: Multi-team groups, points-based qualification")
print(f"   Rounds: {bgmi_tournament.get_total_rounds()}")

print(f"\n📊 Tournament 2 - Valorant 5v5")
print(f"   ID: {valorant_tournament.id}")
print(f"   Teams: {valorant_tournament.current_participants}")
print(f"   Players per team: 5")
print(f"   Format: 2-team matches, win-based qualification")
print(f"   Rounds: {valorant_tournament.get_total_rounds()}")

print(f"\n📈 Total players created: {len(players)}")
print(f"   BGMI uses players 1-32")
print(f"   Valorant uses players 33-40 + remaining slots")

print(f"\n🚀 Next steps:")
print(f"   1. Go to host dashboard → kishan@qodet.com")
print(f"   2. Click 'Manage' on either tournament")
print(f"   3. Both tournaments show {len(bgmi_teams)} registered teams")
print(f"   4. Click 'INITIALIZE MATCHES' to create rounds and groups")
print(f"   5. For BGMI: Groups with 2 teams each (4 teams per round, 2 qualify)")
print(f"   6. For Valorant: 2-team matches (4 matches per round)")
print("=" * 80)
