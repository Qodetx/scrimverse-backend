"""
Script to create a BGMI test tournament and register a player.
Run with: python manage.py shell < create_test_tournament.py
"""
from django.contrib.auth import get_user_model
from accounts.models import HostProfile, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

# 1. Get existing host user
host_user = User.objects.get(email='kishan@qodet.com')
host_profile = HostProfile.objects.get(user=host_user)
print(f"Host: {host_user.username} ({host_user.email})")

# 2. Get existing player user
player_user = User.objects.get(email='kishanbm25@gmail.com')
player_profile = PlayerProfile.objects.get(user=player_user)
print(f"Player: {player_user.username} ({player_user.email})")

# 3. Create BGMI Tournament (ongoing, so we can test room credentials)
now = timezone.now()
tournament = Tournament.objects.create(
    host=host_profile,
    title='[TEST] BGMI Room Credential Test',
    description='Test tournament to verify room ID/password behavior',
    game_name='BGMI',
    game_mode='Squad',
    max_participants=16,
    current_participants=1,
    entry_fee=0.00,
    prize_pool=0.00,
    registration_start=now - timedelta(days=2),
    registration_end=now + timedelta(days=1),
    tournament_start=now - timedelta(hours=1),
    tournament_end=now + timedelta(days=1),
    rules='Test rules',
    status='ongoing',
    rounds=[
        {"round": 1, "max_teams": 16, "qualifying_teams": 8},
        {"round": 2, "max_teams": 8, "qualifying_teams": 1},
    ],
    round_names={"1": "Round 1", "2": "Finals"},
    use_groups_system=True,
)
print(f"Tournament created: ID={tournament.id}, Title='{tournament.title}'")

# 4. Register the player
registration = TournamentRegistration.objects.create(
    tournament=tournament,
    player=player_profile,
    team_name='Alpha Squad',
    status='confirmed',
    payment_status=True,
)
print(f"Registration created: ID={registration.id}, Team='{registration.team_name}'")

print(f"\nDone! Tournament ID: {tournament.id}")
print(f"Now go to the host manage page to configure Round 1 and start a match.")
print(f"Then check the player dashboard at /player/dashboard to see credentials.")
