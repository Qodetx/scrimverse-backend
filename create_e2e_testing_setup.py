#!/usr/bin/env python
import os
import django
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from accounts.models import HostProfile, User, Team, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration

print("\n" + "="*80)
print("🎮 CREATING COMPREHENSIVE END-TO-END TESTING SETUP")
print("="*80)

# Get host
try:
    host_user = User.objects.get(email='kishan@qodet.com')
    host = HostProfile.objects.get(user=host_user)
    print(f"✅ Host: {host.user.email}")
except:
    print("❌ Host not found")
    exit()

# Get/create test player
try:
    player_user = User.objects.get(email='kishanbm25@gmail.com')
    player = PlayerProfile.objects.get(user=player_user)
    print(f"✅ Test Player: {player.user.email}")
except:
    print("❌ Test player not found")
    exit()

now = timezone.now()
tournaments_data = [
    {
        "game": "Valorant",
        "game_mode": "5v5",
        "teams_count": 7,  # ODD number
        "players_per_team": 5,
        "is_5v5": True,
    },
    {
        "game": "BGMI",
        "game_mode": "Squad",
        "teams_count": 6,  # EVEN number
        "players_per_team": 4,
        "is_5v5": False,
    },
    {
        "game": "Call of Duty",
        "game_mode": "Squad",
        "teams_count": 4,  # EVEN number
        "players_per_team": 4,
        "is_5v5": False,
    }
]

player_counter = 1

for idx, tourney_data in enumerate(tournaments_data, 1):
    print(f"\n" + "="*80)
    print(f"🏆 TOURNAMENT {idx}: {tourney_data['game']}")
    print("="*80)
    
    game = tourney_data['game']
    game_mode = tourney_data['game_mode']
    teams_count = tourney_data['teams_count']
    players_per_team = tourney_data['players_per_team']
    
    tournament_start = now + timedelta(days=1)
    tournament_end = now + timedelta(days=2)
    
    tournament = Tournament.objects.create(
        host=host,
        title=f"{game} {game_mode} - E2E Test Tournament {idx}",
        description=f"End-to-end testing tournament for {game}",
        game_name=game,
        game_mode=game_mode,
        max_participants=teams_count,
        entry_fee=0.00,
        prize_pool=0.00,
        registration_start=now,
        registration_end=now + timedelta(minutes=30),
        tournament_start=tournament_start,
        tournament_end=tournament_end,
        status="upcoming",
        use_groups_system=True,
        event_mode="TOURNAMENT",
    )
    
    # Configure rounds
    if teams_count >= 4:
        tournament.rounds = [
            {"round": 1, "max_teams": teams_count, "qualifying_teams": teams_count // 2},
            {"round": 2, "max_teams": teams_count // 2, "qualifying_teams": teams_count // 4},
            {"round": 3, "max_teams": teams_count // 4, "qualifying_teams": 1},
        ]
    else:
        tournament.rounds = [
            {"round": 1, "max_teams": teams_count, "qualifying_teams": 1},
        ]
    
    tournament.round_names = {
        "1": "Qualifiers",
        "2": "Semi Finals",
        "3": "Grand Finals"
    }
    tournament.save()
    
    print(f"\n✅ Created: {tournament.title}")
    print(f"   ID: {tournament.id}")
    print(f"   Teams: {teams_count}")
    print(f"   Players per team: {players_per_team}")
    
    # Create teams and register players
    print(f"\n📝 Creating {teams_count} teams...")
    
    for team_num in range(1, teams_count + 1):
        team_name = f"{game} Team {team_num}"
        team, _ = Team.objects.get_or_create(
            name=team_name,
            defaults={'captain': host_user}
        )
        
        # Create and register players for this team
        for player_slot in range(players_per_team):
            # For the first team, add the test player
            if team_num == 1 and player_slot == 0:
                # Register test player to first team
                TournamentRegistration.objects.create(
                    tournament=tournament,
                    team=team,
                    player=player,
                    status="approved"
                )
                print(f"  ✅ {team_name}: {player.user.email} (TEST PLAYER)")
            else:
                # Create new dummy player
                user, _ = User.objects.get_or_create(
                    username=f"e2e_p{player_counter}",
                    defaults={
                        'email': f'e2e_player{player_counter}@test.com',
                        'user_type': 'player'
                    }
                )
                profile, _ = PlayerProfile.objects.get_or_create(
                    user=user,
                    defaults={'in_game_name': f'E2E_Player{player_counter}'}
                )
                
                TournamentRegistration.objects.create(
                    tournament=tournament,
                    team=team,
                    player=profile,
                    status="approved"
                )
                player_counter += 1
        
        if team_num % 2 == 0 or team_num == teams_count:
            print(f"  ✅ {team_name}: {players_per_team} players")

# Verify structure
print(f"\n" + "="*80)
print("✅ VERIFICATION")
print("="*80)

for idx, tourney_data in enumerate(tournaments_data, 1):
    tournament = Tournament.objects.filter(
        host=host,
        game_name=tourney_data['game']
    ).order_by('-created_at').first()
    
    total_regs = TournamentRegistration.objects.filter(tournament=tournament).count()
    unique_teams = TournamentRegistration.objects.filter(tournament=tournament).values('team').distinct().count()
    
    print(f"\n{tourney_data['game']} Tournament (ID: {tournament.id})")
    print(f"  Total Registrations: {total_regs}")
    print(f"  Total Teams: {unique_teams}")
    print(f"  Status: {tournament.status}")

print(f"\n" + "="*80)
print("✅ END-TO-END TESTING SETUP COMPLETE!")
print("="*80)
print(f"""
NEXT STEPS TO TEST:
===================

1. **Host Dashboard Testing**
   - Login as: kishan@qodet.com
   - View all 3 tournaments created
   - Check team counts and player counts

2. **Tournament Management**
   - Start Round 1 on each tournament
   - Configure groups
   - Test Bulk Schedule feature

3. **Player Dashboard Testing**
   - Login as: kishanbm25@gmail.com
   - Verify tournament listings
   - Check player is in first team of each tournament
   - View schedule/matches

4. **Scoring & Results**
   - Add match results
   - Test different result modals (5v5, squad)
   - Verify points system

5. **Leaderboards**
   - Check host dashboard stats
   - Verify for different tournament types
""")
