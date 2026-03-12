#!/usr/bin/env python
"""
Insert a test tournament (BGMI Squad, ongoing) with 8 registered teams
and 2 rounds so you can test the Bulk Schedule feature in ManageTournament.

Run from the backend root:
    python insert_bulk_schedule_test.py
"""
import os
import django
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, HostProfile, TeamMember
from tournaments.models import Tournament, TournamentRegistration, Team

# ── 1. Get host ────────────────────────────────────────────────────────────────
host = HostProfile.objects.first()
if not host:
    print("❌  No HostProfile found. Create a host account first.")
    exit(1)
print(f"✅  Using host: {host.user.username}")

# ── 2. Create tournament ───────────────────────────────────────────────────────
now = timezone.now()
tournament, created = Tournament.objects.get_or_create(
    title="BGMI Bulk-Schedule Test Tournament",
    defaults={
        "host": host,
        "game_name": "BGMI",
        "game_mode": "Squad",
        "description": "Test tournament for bulk schedule feature testing.",
        "max_participants": 8,
        "entry_fee": 0,
        "prize_pool": 5000,
        "registration_start": now - timedelta(days=3),
        "registration_end": now - timedelta(days=1),
        "tournament_start": now,
        "tournament_end": now + timedelta(days=2),
        "status": "ongoing",
        "current_round": 1,
        "rules": "Standard BGMI rules. No teaming.",
        "round_status": {"1": "pending", "2": "pending"},
        "rounds": [
            {"round": 1, "max_teams": 8, "qualifying_teams": 4, "name": "Qualifiers"},
            {"round": 2, "max_teams": 4, "qualifying_teams": 2, "name": "Semi-Finals"},
        ],
        "placement_points": {"1": 15, "2": 12, "3": 10, "4": 8, "5": 6, "6": 4, "7": 2, "8": 1},
    },
)
verb = "Created" if created else "Found existing"
print(f"{'✅' if created else 'ℹ️ '}  {verb} tournament: {tournament.title} (ID: {tournament.id})")

# ── 3. Create 8 test player accounts ──────────────────────────────────────────
players_data = [
    {"email": f"bgmiplayer{i}@test.com", "username": f"bgmiplayer{i}", "phone": f"98000000{i:02d}"}
    for i in range(1, 9)
]

players = []
for d in players_data:
    user = User.objects.filter(email=d["email"]).first() or \
           User.objects.filter(username=d["username"]).first()
    if not user:
        user = User.objects.create(
            email=d["email"],
            username=d["username"],
            user_type="player",
            phone_number=d["phone"],
            is_email_verified=True,
        )
        user.set_password("testpass123")
        user.save()
        PlayerProfile.objects.get_or_create(user=user)
        print(f"  ✅  Created player: {user.username}")
    else:
        print(f"  ℹ️   Found player: {user.username}")
    players.append(user)

# ── 4. Create 8 teams and register them ───────────────────────────────────────
print(f"\n🎮  Creating 8 teams & registrations for tournament {tournament.id}...")
for i, captain in enumerate(players):
    team_name = f"BGMI Squad {chr(65 + i)}"   # Squad A … Squad H
    team, t_created = Team.objects.get_or_create(
        name=team_name,
        defaults={"captain": captain, "is_temporary": False},
    )
    if t_created:
        print(f"  ✅  Created team: {team_name}")
        # Add captain as team member
        TeamMember.objects.get_or_create(
            team=team, user=captain,
            defaults={"username": captain.username, "is_captain": True},
        )
    else:
        print(f"  ℹ️   Found team: {team_name}")

    captain_profile, _ = PlayerProfile.objects.get_or_create(user=captain)

    # Register to tournament (skip if already registered)
    reg, r_created = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        team=team,
        defaults={
            "player": captain_profile,
            "status": "confirmed",
            "payment_status": True,
            "team_name": team_name,
            "team_members": [captain.username],
        },
    )
    if r_created:
        print(f"    ✅  Registered {team_name}")
    else:
        print(f"    ℹ️   Already registered: {team_name}")

print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Done!

Tournament ID : {tournament.id}
Title         : {tournament.title}
Game          : {tournament.game_name} | {tournament.game_mode}
Status        : {tournament.status}
Teams         : 8 registered

Manage URL:
  http://localhost:3000/host/tournaments/{tournament.id}/manage

Use the Bulk Schedule button in Round 1 to test map selection with "Other".
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
