"""
Script to create a COD 5v5 test tournament with completed matches and scores.
Run with: python manage.py shell < create_5v5_test_tournament.py
"""
from django.contrib.auth import get_user_model
from accounts.models import HostProfile, PlayerProfile, Team
from tournaments.models import Tournament, TournamentRegistration, Group, Match, MatchScore
from django.utils import timezone
from datetime import timedelta

User = get_user_model()
now = timezone.now()

# ===== 1. Get/Create Users =====
host_user = User.objects.get(email='kishan@qodet.com')
host_profile = HostProfile.objects.get(user=host_user)
print(f"Host: {host_user.username}")

# Get or create 4 player users
player_emails = [
    'kishanbm25@gmail.com',  # Real player
    'testplayer2@test.com',
    'testplayer3@test.com',
    'testplayer4@test.com',
]
player_profiles = []

for email in player_emails:
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
        print(f"  Created user: {user.username}")

    profile, _ = PlayerProfile.objects.get_or_create(user=user)
    player_profiles.append(profile)
    print(f"  Player: {user.username} (id={profile.id})")

# ===== 2. Create Team objects =====
team_names = ['Team Alpha', 'Team Bravo', 'Team Charlie', 'Team Delta']
teams = []
for i, name in enumerate(team_names):
    team, created = Team.objects.get_or_create(
        name=name,
        captain=player_profiles[i].user,
        defaults={'is_temporary': True}
    )
    teams.append(team)
    print(f"  Team: {name} (id={team.id})")

# ===== 3. Create Tournament =====
tournament = Tournament.objects.create(
    host=host_profile,
    title='[PTS TEST] COD 5v5 With Scores',
    description='Test 5v5 tournament with completed matches and scores',
    game_name='COD',
    game_mode='5v5',
    max_participants=8,
    current_participants=4,
    entry_fee=0.00,
    prize_pool=0.00,
    registration_start=now - timedelta(days=3),
    registration_end=now - timedelta(days=1),
    tournament_start=now - timedelta(hours=2),
    tournament_end=now + timedelta(days=1),
    rules='Test rules for COD 5v5',
    status='ongoing',
    current_round=1,
    rounds=[
        {"round": 1, "max_teams": 4, "qualifying_teams": 2},
    ],
    round_names={"1": "Round 1"},
    use_groups_system=True,
)
print(f"\nTournament created: ID={tournament.id}, Title='{tournament.title}'")

# ===== 4. Register Players =====
registrations = []
for i, profile in enumerate(player_profiles):
    reg = TournamentRegistration.objects.create(
        tournament=tournament,
        player=profile,
        team=teams[i],
        team_name=team_names[i],
        status='confirmed',
        payment_status=True,
    )
    registrations.append(reg)
    print(f"  Registration: {reg.team_name} (reg_id={reg.id}, team_id={teams[i].id})")

# ===== 5. Create Groups (Lobbies) =====
# Lobby 1: Team Alpha vs Team Bravo
group1 = Group.objects.create(
    tournament=tournament,
    round_number=1,
    group_name='Lobby 1',
    qualifying_teams=1,
    status='completed',
)
group1.teams.set([registrations[0], registrations[1]])

# Lobby 2: Team Charlie vs Team Delta
group2 = Group.objects.create(
    tournament=tournament,
    round_number=1,
    group_name='Lobby 2',
    qualifying_teams=1,
    status='completed',
)
group2.teams.set([registrations[2], registrations[3]])

print(f"\n  Group 1: {group1.group_name} (id={group1.id}) - {team_names[0]} vs {team_names[1]}")
print(f"  Group 2: {group2.group_name} (id={group2.id}) - {team_names[2]} vs {team_names[3]}")

# ===== 6. Create Matches =====
match1 = Match.objects.create(
    group=group1,
    match_number=1,
    status='completed',
    started_at=now - timedelta(hours=1),
    ended_at=now - timedelta(minutes=30),
)

match2 = Match.objects.create(
    group=group2,
    match_number=1,
    status='completed',
    started_at=now - timedelta(hours=1),
    ended_at=now - timedelta(minutes=30),
)

print(f"\n  Match 1 (Lobby 1): id={match1.id}")
print(f"  Match 2 (Lobby 2): id={match2.id}")

# ===== 7. Create Match Scores =====
# Lobby 1: Team Alpha wins 16-8
score1a = MatchScore.objects.create(
    match=match1,
    team=registrations[0],  # Team Alpha
    wins=1,
    position_points=16,
    kill_points=0,
)
score1b = MatchScore.objects.create(
    match=match1,
    team=registrations[1],  # Team Bravo
    wins=0,
    position_points=8,
    kill_points=0,
)

# Lobby 2: Team Delta wins 13-10
score2a = MatchScore.objects.create(
    match=match2,
    team=registrations[2],  # Team Charlie
    wins=0,
    position_points=10,
    kill_points=0,
)
score2b = MatchScore.objects.create(
    match=match2,
    team=registrations[3],  # Team Delta
    wins=1,
    position_points=13,
    kill_points=0,
)

# Set match winners
match1.winner = registrations[0]  # Team Alpha
match1.save()
match2.winner = registrations[3]  # Team Delta
match2.save()

# Set group winners
group1.winner = registrations[0]  # Team Alpha
group1.save()
group2.winner = registrations[3]  # Team Delta
group2.save()

print(f"\n  Lobby 1: {team_names[0]} {score1a.total_points} – {score1b.total_points} {team_names[1]} (Winner: {team_names[0]})")
print(f"  Lobby 2: {team_names[2]} {score2a.total_points} – {score2b.total_points} {team_names[3]} (Winner: {team_names[3]})")

print(f"\n=== DONE ===")
print(f"Tournament ID: {tournament.id}")
print(f"Go to player dashboard as kishanbm25@gmail.com")
print(f"Open the points table for '[PTS TEST] COD 5v5 With Scores'")
print(f"You should see Lobby 1 (Alpha 16–8 Bravo) and Lobby 2 (Charlie 10–13 Delta)")
