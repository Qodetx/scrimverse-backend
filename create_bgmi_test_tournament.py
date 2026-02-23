#!/usr/bin/env python
"""
Create a BGMI Squad test tournament with 12 teams for testing BR flow.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration

# Find first host
host_user = User.objects.filter(user_type='host').first()
if not host_user:
    print("ERROR: No host user found")
    exit(1)
host = HostProfile.objects.get(user=host_user)
print(f"Using host: {host_user.username}")

now = timezone.now()

# Create tournament
tournament = Tournament.objects.create(
    host=host,
    title="BGMI Squad Test Tournament",
    description="Test BGMI tournament for BR flow testing",
    game_name="BGMI",
    game_mode="Squad",
    max_participants=12,
    current_participants=0,
    entry_fee=0,
    prize_pool=50000,
    registration_start=now - timedelta(days=5),
    registration_end=now - timedelta(days=1),
    tournament_start=now - timedelta(hours=2),
    tournament_end=now + timedelta(days=1),
    tournament_date=now.date(),
    tournament_time=now.time(),
    status="ongoing",
    event_mode="TOURNAMENT",
    rules="Test BGMI tournament rules",
    rounds=[
        {"round": 1, "max_teams": 12, "qualifying_teams": 6},
        {"round": 2, "max_teams": 6, "qualifying_teams": 3},
        {"round": 3, "max_teams": 3, "qualifying_teams": 1},
    ],
    round_names={"1": "Qualifiers", "2": "Semi-Finals", "3": "Grand Finals"},
    current_round=0,
    round_status={},
    selected_teams={},
    plan_type="basic",
    plan_price=0,
    plan_payment_status=True,
)
print(f"Created tournament: {tournament.title} (ID: {tournament.id})")

# Team names for BGMI
team_names = [
    "Soul Snippers",
    "GodL Esports",
    "Blind Esports",
    "OR Esports",
    "Team XO",
    "Team Insane",
    "Marcos Gaming",
    "Team Mayhem",
    "Gladiators Esports",
    "Team IND",
    "Stalwart Esports",
    "Velocity Gaming",
]

# Create player + team + registration for each
for i, team_name in enumerate(team_names):
    username = f"bgmi_player_{i+1}"
    email = f"bgmi_player_{i+1}@test.com"

    # Create user
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "user_type": "player"}
    )
    user.set_password("test1234")
    user.save()

    # Create player profile
    player, _ = PlayerProfile.objects.get_or_create(user=user)

    # Create team
    team, _ = Team.objects.get_or_create(
        name=team_name,
        defaults={"created_by": player}
    )

    # Create registration
    reg, created = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        team=team,
        defaults={
            "player": player,
            "status": "confirmed",
            "team_name": team_name,
        }
    )
    if not created:
        reg.status = "confirmed"
        reg.save()

    print(f"  [{i+1:2d}] {team_name} — reg ID: {reg.id}")

# Update current_participants
confirmed_count = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()
tournament.current_participants = confirmed_count
tournament.save(update_fields=["current_participants"])

print(f"\n=== DONE ===")
print(f"Tournament ID: {tournament.id}")
print(f"Confirmed teams: {confirmed_count}")
print(f"Rounds: {tournament.rounds}")
print(f"\nNow go to: http://localhost:3000/tournaments/{tournament.id}/manage")
