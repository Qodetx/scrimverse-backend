"""
Create a complete Valorant 5v5 tournament with all rounds completed.
- Host: kishan@qodet.com
- Player: kishanbm25@gmail.com (Team Alpha - progresses through all rounds to win)
- 20 teams, 4 rounds: R1 (10 lobbies), R2 (5 lobbies), Semi (2-3 lobbies), Finals (1 lobby)
- All rounds completed with scores matching the image format (single total points per team)

Run with: python manage.py shell < create_valorant_5v5_complete.py
"""
from django.contrib.auth import get_user_model
from accounts.models import HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import (
    Tournament, TournamentRegistration, Group, Match, MatchScore, RoundScore
)
from django.utils import timezone
from datetime import timedelta
import random

User = get_user_model()
now = timezone.now()

# Valorant maps for variety
VALORANT_MAPS = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze', 'Fracture', 'Pearl', 'Lotus', 'Sunset']

# ===== 1. Get Host =====
host_user = User.objects.get(email='kishan@qodet.com')
host_profile = HostProfile.objects.get(user=host_user)
print(f"Host: {host_user.username} (id={host_user.id})")

# ===== 2. Get/Create Players =====
# kishanbm25@gmail.com is Team Alpha captain (will win the tournament)
team_data = [
    {'name': 'Team Alpha',    'captain_email': 'kishanbm25@gmail.com'},
    {'name': 'Team Bravo',    'captain_email': 'val_bravo@test.com'},
    {'name': 'Team Charlie',  'captain_email': 'val_charlie@test.com'},
    {'name': 'Team Delta',    'captain_email': 'val_delta@test.com'},
    {'name': 'Team Echo',     'captain_email': 'val_echo@test.com'},
    {'name': 'Team Foxtrot',  'captain_email': 'val_foxtrot@test.com'},
    {'name': 'Team Ghost',    'captain_email': 'val_ghost@test.com'},
    {'name': 'Team Havoc',    'captain_email': 'val_havoc@test.com'},
    {'name': 'Team Inferno',  'captain_email': 'val_inferno@test.com'},
    {'name': 'Team Jaguar',   'captain_email': 'val_jaguar@test.com'},
    {'name': 'Team Knight',   'captain_email': 'val_knight@test.com'},
    {'name': 'Team Legion',   'captain_email': 'val_legion@test.com'},
    {'name': 'Team Maverick', 'captain_email': 'val_maverick@test.com'},
    {'name': 'Team Nova',     'captain_email': 'val_nova@test.com'},
    {'name': 'Team Omega',    'captain_email': 'val_omega@test.com'},
    {'name': 'Team Phoenix',  'captain_email': 'val_phoenix@test.com'},
    {'name': 'Team Raptor',   'captain_email': 'val_raptor@test.com'},
    {'name': 'Team Storm',    'captain_email': 'val_storm@test.com'},
    {'name': 'Team Titan',    'captain_email': 'val_titan@test.com'},
    {'name': 'Team Viper',    'captain_email': 'val_viper@test.com'},
]

player_profiles = []
teams = []

for td in team_data:
    email = td['captain_email']
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': email.split('@')[0],
            'user_type': 'player',
            'is_email_verified': True,
        }
    )
    if created:
        user.set_password('test12345')
        user.save()

    profile, _ = PlayerProfile.objects.get_or_create(user=user)
    player_profiles.append(profile)

    team, _ = Team.objects.get_or_create(
        name=td['name'],
        captain=user,
        defaults={'is_temporary': True}
    )
    teams.append(team)

print(f"Created/found {len(teams)} teams")

# ===== 3. Create Tournament =====
tournament = Tournament.objects.create(
    host=host_profile,
    title='Demo Valorant Masters',
    description='Valorant 5v5 Masters - Complete tournament with all rounds played',
    game_name='Valorant',
    game_mode='5v5',
    max_participants=20,
    current_participants=20,
    entry_fee=0.00,
    prize_pool=10000.00,
    prize_distribution={"1st": 5000, "2nd": 3000, "3rd": 1500, "4th": 500},
    registration_start=now - timedelta(days=7),
    registration_end=now - timedelta(days=5),
    tournament_start=now - timedelta(days=3),
    tournament_end=now - timedelta(hours=1),
    rules='Standard Valorant competitive rules. Best of 1 per lobby.',
    status='completed',
    current_round=4,
    rounds=[
        {"round": 1, "max_teams": 20, "qualifying_teams": 10},
        {"round": 2, "max_teams": 10, "qualifying_teams": 5},
        {"round": 3, "max_teams": 4, "qualifying_teams": 2},  # Semi (bye team gets through)
        {"round": 4, "max_teams": 2, "qualifying_teams": 1},  # Finals
    ],
    round_names={"1": "R1", "2": "R2", "3": "Semi", "4": "Finals"},
    round_status={
        "1": {"status": "completed"},
        "2": {"status": "completed"},
        "3": {"status": "completed"},
        "4": {"status": "completed"},
    },
    use_groups_system=True,
)
print(f"\nTournament created: ID={tournament.id}, Title='{tournament.title}'")

# ===== 4. Register All Teams =====
registrations = []
for i, (profile, team) in enumerate(zip(player_profiles, teams)):
    reg = TournamentRegistration.objects.create(
        tournament=tournament,
        player=profile,
        team=team,
        team_name=team_data[i]['name'],
        status='confirmed',
        payment_status=True,
    )
    registrations.append(reg)

print(f"Registered {len(registrations)} teams")

# Helper: map team name to registration
reg_by_name = {r.team_name: r for r in registrations}


def create_lobby(tournament, round_number, lobby_name, team_a_reg, team_b_reg,
                 team_a_pts, team_b_pts, map_name=None):
    """Create a completed lobby with a single match and scores."""
    group = Group.objects.create(
        tournament=tournament,
        round_number=round_number,
        group_name=lobby_name,
        qualifying_teams=1,
        status='completed',
    )
    group.teams.set([team_a_reg, team_b_reg])

    match = Match.objects.create(
        group=group,
        match_number=1,
        status='completed',
        map_name=map_name,
        started_at=now - timedelta(days=4-round_number, hours=random.randint(1,5)),
        ended_at=now - timedelta(days=4-round_number, minutes=random.randint(10,55)),
    )

    # Team A score
    MatchScore.objects.create(
        match=match,
        team=team_a_reg,
        wins=1 if team_a_pts > team_b_pts else 0,
        position_points=team_a_pts,
        kill_points=0,
    )
    # Team B score
    MatchScore.objects.create(
        match=match,
        team=team_b_reg,
        wins=1 if team_b_pts > team_a_pts else 0,
        position_points=team_b_pts,
        kill_points=0,
    )

    # Set match winner
    winner = team_a_reg if team_a_pts > team_b_pts else team_b_reg
    match.winner = winner
    match.save()

    # Set group winner
    group.winner = winner
    group.save()

    # Create/Update RoundScores
    for team_reg, pts in [(team_a_reg, team_a_pts), (team_b_reg, team_b_pts)]:
        rs, _ = RoundScore.objects.get_or_create(
            tournament=tournament,
            round_number=round_number,
            team=team_reg,
            defaults={'position_points': pts, 'kill_points': 0}
        )
        if not _:
            rs.position_points += pts
            rs.kill_points = 0
            rs.save()

    winner_name = winner.team_name
    loser_name = team_b_reg.team_name if winner == team_a_reg else team_a_reg.team_name
    print(f"  {lobby_name} ({map_name}): {team_a_reg.team_name} {team_a_pts} - {team_b_pts} {team_b_reg.team_name} | Winner: {winner_name}")

    return group, winner


# ===========================================================================
# ROUND 1: 20 teams → 10 lobbies → 10 winners advance
# ===========================================================================
print(f"\n--- ROUND 1 (10 Lobbies) ---")

# Matchups and scores (Team Alpha = kishanbm25@gmail.com's team wins)
r1_matchups = [
    ('Team Alpha',    'Team Bravo',    16, 32, 'Bind'),     # Bravo wins (different from usual to show variety) - WAIT, Alpha should advance
]

# Actually, let's make Team Alpha WIN so kishanbm25@gmail.com progresses
# Scores like the screenshot: total points per team (like Valorant round scores)
r1_matchups = [
    ('Team Alpha',    'Team Bravo',    32, 16, 'Bind'),      # Alpha wins
    ('Team Charlie',  'Team Delta',    29, 24, 'Haven'),     # Charlie wins
    ('Team Echo',     'Team Foxtrot',  32, 17, 'Split'),     # Echo wins
    ('Team Ghost',    'Team Havoc',    13, 21, 'Ascent'),    # Havoc wins
    ('Team Inferno',  'Team Jaguar',   48, 39, 'Icebox'),    # Inferno wins
    ('Team Knight',   'Team Legion',   25, 18, 'Breeze'),    # Knight wins
    ('Team Maverick', 'Team Nova',     14, 27, 'Fracture'),  # Nova wins
    ('Team Omega',    'Team Phoenix',  31, 22, 'Pearl'),     # Omega wins
    ('Team Raptor',   'Team Storm',    19, 26, 'Lotus'),     # Storm wins
    ('Team Titan',    'Team Viper',    33, 28, 'Sunset'),    # Titan wins
]

r1_winners = []
for i, (team_a, team_b, pts_a, pts_b, map_name) in enumerate(r1_matchups):
    _, winner = create_lobby(
        tournament, 1, f'Lobby {i+1}',
        reg_by_name[team_a], reg_by_name[team_b],
        pts_a, pts_b, map_name
    )
    r1_winners.append(winner)

# Store selected teams for round 1
tournament.selected_teams['1'] = [w.id for w in r1_winners]
tournament.save()

# R1 winners: Alpha, Charlie, Echo, Havoc, Inferno, Knight, Nova, Omega, Storm, Titan

# ===========================================================================
# ROUND 2: 10 winners → 5 lobbies → 5 winners advance
# ===========================================================================
print(f"\n--- ROUND 2 (5 Lobbies) ---")

r2_matchups = [
    ('Team Alpha',   'Team Charlie',  26, 19, 'Haven'),     # Alpha wins
    ('Team Echo',    'Team Havoc',    21, 28, 'Ascent'),    # Havoc wins
    ('Team Inferno', 'Team Knight',   35, 30, 'Icebox'),    # Inferno wins
    ('Team Nova',    'Team Omega',    17, 24, 'Breeze'),    # Omega wins
    ('Team Storm',   'Team Titan',    22, 15, 'Split'),     # Storm wins
]

r2_winners = []
for i, (team_a, team_b, pts_a, pts_b, map_name) in enumerate(r2_matchups):
    _, winner = create_lobby(
        tournament, 2, f'Lobby {i+1}',
        reg_by_name[team_a], reg_by_name[team_b],
        pts_a, pts_b, map_name
    )
    r2_winners.append(winner)

tournament.selected_teams['2'] = [w.id for w in r2_winners]
tournament.save()

# R2 winners: Alpha, Havoc, Inferno, Omega, Storm

# ===========================================================================
# SEMI-FINALS: 5 winners → need 4 for 2 lobbies, 1 gets bye
# But round config says max_teams: 4, qualifying: 2
# We'll use 4 teams (drop the 5th or give bye). Let's do 2 lobbies of 2.
# With 5 teams and qualifying_teams=2, we pick top 4 by points and 1 bye.
# Simpler: just use 4 teams in Semi (Storm gets auto-bye/eliminated)
# Actually let's keep it clean: 4 teams → 2 lobbies → 2 winners
# ===========================================================================
print(f"\n--- SEMI-FINALS (2 Lobbies) ---")

# Select top 4 from R2 (drop Storm who had lowest score)
semi_teams = [reg_by_name['Team Alpha'], reg_by_name['Team Havoc'],
              reg_by_name['Team Inferno'], reg_by_name['Team Omega']]

semi_matchups = [
    ('Team Alpha',   'Team Omega',    29, 21, 'Bind'),      # Alpha wins
    ('Team Havoc',   'Team Inferno',  24, 31, 'Lotus'),     # Inferno wins
]

semi_winners = []
for i, (team_a, team_b, pts_a, pts_b, map_name) in enumerate(semi_matchups):
    _, winner = create_lobby(
        tournament, 3, f'Lobby {i+1}',
        reg_by_name[team_a], reg_by_name[team_b],
        pts_a, pts_b, map_name
    )
    semi_winners.append(winner)

tournament.selected_teams['3'] = [w.id for w in semi_winners]
tournament.save()

# Semi winners: Alpha, Inferno

# ===========================================================================
# FINALS: 2 teams → 1 lobby → 1 winner (Team Alpha wins!)
# ===========================================================================
print(f"\n--- FINALS (1 Lobby) ---")

finals_matchup = ('Team Alpha', 'Team Inferno', 38, 29, 'Haven')
team_a, team_b, pts_a, pts_b, map_name = finals_matchup

_, final_winner = create_lobby(
    tournament, 4, 'Grand Final',
    reg_by_name[team_a], reg_by_name[team_b],
    pts_a, pts_b, map_name
)

tournament.selected_teams['4'] = [final_winner.id]
tournament.winners = {'4': final_winner.id}
tournament.save()

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*60}")
print(f"TOURNAMENT COMPLETE!")
print(f"{'='*60}")
print(f"Tournament ID: {tournament.id}")
print(f"Title: {tournament.title}")
print(f"Game: {tournament.game_name} ({tournament.game_mode})")
print(f"Rounds: R1 → R2 → Semi → Finals")
print(f"Winner: {final_winner.team_name}")
print(f"")
print(f"Player kishanbm25@gmail.com plays as '{reg_by_name['Team Alpha'].team_name}'")
print(f"Team Alpha path: R1 (beat Bravo 32-16) → R2 (beat Charlie 26-19) → Semi (beat Omega 29-21) → Finals (beat Inferno 38-29)")
print(f"")
print(f"Login as kishanbm25@gmail.com to see this in the player dashboard.")
print(f"{'='*60}")
