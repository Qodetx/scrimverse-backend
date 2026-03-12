#!/usr/bin/env python
"""
Create two LIVE (ongoing) test tournaments:
  1. COD 5v5 — 8 teams with 5 members each
  2. BGMI Squad — 16 teams with 4 members each

Both tournaments are in 'ongoing' status (started 2 hours ago, ends tomorrow).
Round 1 is ready to be configured but not yet started, so you can:
  - Open the Configure Round modal
  - See the round reset feature in action
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.utils import timezone
from datetime import timedelta
from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import Tournament, TournamentRegistration

now = timezone.now()


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def get_host():
    host_user = User.objects.filter(user_type="host").first()
    if not host_user:
        print("ERROR: No host user found in DB. Create one first.")
        exit(1)
    return HostProfile.objects.get(user=host_user)


def make_player(username, email):
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "user_type": "player"},
    )
    user.set_password("test1234")
    user.save()
    player, _ = PlayerProfile.objects.get_or_create(user=user)
    return user, player


def make_team_with_members(team_name, captain_user, captain_player, member_usernames):
    """Create team + captain member + additional members."""
    team, _ = Team.objects.get_or_create(
        name=team_name,
        defaults={"captain": captain_user},
    )

    # Captain member
    TeamMember.objects.get_or_create(
        team=team,
        username=captain_user.username,
        defaults={"user": captain_user, "is_captain": True},
    )

    # Other members
    for i, uname in enumerate(member_usernames):
        email = f"{uname}@test.com"
        muser, mplayer = make_player(uname, email)
        TeamMember.objects.get_or_create(
            team=team,
            username=uname,
            defaults={"user": muser, "is_captain": False},
        )

    return team


def register_team(tournament, team, captain_player):
    reg, _ = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        team=team,
        defaults={
            "player": captain_player,
            "status": "confirmed",
            "team_name": team.name,
        },
    )
    reg.status = "confirmed"
    reg.save()
    return reg


# ─────────────────────────────────────────────────────────────
# 1. COD 5v5 Live Tournament
# ─────────────────────────────────────────────────────────────

def create_cod_live():
    host = get_host()

    tournament = Tournament.objects.create(
        host=host,
        title="COD 5v5 Live Test",
        game_name="COD",
        game_mode="5v5",
        description="Live COD 5v5 tournament for round configuration testing. 8 teams, 2 rounds.",
        max_participants=8,
        entry_fee=0,
        prize_pool=20000,
        registration_start=now - timedelta(days=5),
        registration_end=now - timedelta(hours=3),
        tournament_start=now - timedelta(hours=2),
        tournament_end=now + timedelta(days=1),
        tournament_date=now.date(),
        tournament_time=now.time(),
        status="ongoing",
        event_mode="TOURNAMENT",
        rules="Standard COD 5v5 rules. BO1 Semi-Finals, BO3 Grand Finals.",
        rounds=[
            {"round": 1, "max_teams": 8, "qualifying_teams": 4},
            {"round": 2, "max_teams": 4, "qualifying_teams": 1},
        ],
        round_names={"1": "Semi-Finals", "2": "Grand Finals"},
        placement_points={"1": 200, "2": 150, "3": 100, "4": 75},
        prize_distribution={"1st": 10000, "2nd": 6000, "3rd": 4000},
        current_round=0,
        round_status={},
        selected_teams={},
        plan_type="basic",
        plan_price=0,
        plan_payment_status=True,
    )
    print(f"\n✅ Created COD Tournament: {tournament.title} (ID: {tournament.id})")

    # 8 teams × 5 members each
    cod_teams = [
        ("FrostBite Ops",    ["fb_player2",  "fb_player3",  "fb_player4",  "fb_player5"]),
        ("Shadow Squadron",  ["ss_player2",  "ss_player3",  "ss_player4",  "ss_player5"]),
        ("Tactical Strike",  ["ts_player2",  "ts_player3",  "ts_player4",  "ts_player5"]),
        ("Phantom Elite",    ["pe_player2",  "pe_player3",  "pe_player4",  "pe_player5"]),
        ("Viper Force",      ["vf_player2",  "vf_player3",  "vf_player4",  "vf_player5"]),
        ("Iron Wolves",      ["iw_player2",  "iw_player3",  "iw_player4",  "iw_player5"]),
        ("Neon Raiders",     ["nr_player2",  "nr_player3",  "nr_player4",  "nr_player5"]),
        ("Apex Hunters",     ["ah_player2",  "ah_player3",  "ah_player4",  "ah_player5"]),
    ]

    for i, (team_name, members) in enumerate(cod_teams, 1):
        prefix = team_name.lower().replace(" ", "_")
        cap_uname = f"cod_{prefix}_cap"
        cap_user, cap_player = make_player(cap_uname, f"{cap_uname}@test.com")
        member_unames = [f"cod_{m}" for m in members]
        team = make_team_with_members(team_name, cap_user, cap_player, member_unames)
        register_team(tournament, team, cap_player)
        print(f"  [{i:2d}] {team_name} ({1 + len(members)} members)")

    confirmed = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()
    tournament.current_participants = confirmed
    tournament.save(update_fields=["current_participants"])

    print(f"\n  Confirmed teams: {confirmed}")
    print(f"  👉 http://localhost:3000/tournaments/{tournament.id}/manage")
    return tournament


# ─────────────────────────────────────────────────────────────
# 2. BGMI Squad Live Tournament
# ─────────────────────────────────────────────────────────────

def create_bgmi_live():
    host = get_host()

    tournament = Tournament.objects.create(
        host=host,
        title="BGMI Squad Live Test",
        game_name="BGMI",
        game_mode="Squad",
        description="Live BGMI Squad tournament for BR round configuration testing. 16 teams, 3 rounds.",
        max_participants=16,
        entry_fee=0,
        prize_pool=50000,
        registration_start=now - timedelta(days=5),
        registration_end=now - timedelta(hours=3),
        tournament_start=now - timedelta(hours=2),
        tournament_end=now + timedelta(days=1),
        tournament_date=now.date(),
        tournament_time=now.time(),
        status="ongoing",
        event_mode="TOURNAMENT",
        rules="Standard BGMI Squad BR rules. Top 8 qualify from each round.",
        rounds=[
            {"round": 1, "max_teams": 16, "qualifying_teams": 8},
            {"round": 2, "max_teams": 8,  "qualifying_teams": 4},
            {"round": 3, "max_teams": 4,  "qualifying_teams": 1},
        ],
        round_names={"1": "Qualifiers", "2": "Semi-Finals", "3": "Grand Finals"},
        placement_points={"1": 12, "2": 9, "3": 7, "4": 5, "5": 4, "6": 3, "7": 2, "8": 1},
        prize_distribution={"1st": 25000, "2nd": 15000, "3rd": 10000},
        current_round=0,
        round_status={},
        selected_teams={},
        plan_type="basic",
        plan_price=0,
        plan_payment_status=True,
    )
    print(f"\n✅ Created BGMI Tournament: {tournament.title} (ID: {tournament.id})")

    bgmi_teams = [
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
        "Enigma Gaming",
        "7Sea Esports",
        "R Esports",
        "Revenant Esports",
    ]

    for i, team_name in enumerate(bgmi_teams, 1):
        prefix = f"bgmi_{i}"
        cap_uname = f"{prefix}_cap"
        cap_user, cap_player = make_player(cap_uname, f"{cap_uname}@test.com")
        # 3 additional members (squad of 4)
        member_unames = [f"{prefix}_m{j}" for j in range(2, 5)]
        team = make_team_with_members(team_name, cap_user, cap_player, member_unames)
        register_team(tournament, team, cap_player)
        print(f"  [{i:2d}] {team_name} (4 members)")

    confirmed = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()
    tournament.current_participants = confirmed
    tournament.save(update_fields=["current_participants"])

    print(f"\n  Confirmed teams: {confirmed}")
    print(f"  👉 http://localhost:3000/tournaments/{tournament.id}/manage")
    return tournament


# ─────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Creating LIVE test tournaments...")
    print("=" * 60)

    cod = create_cod_live()
    bgmi = create_bgmi_live()

    print("\n" + "=" * 60)
    print("ALL DONE")
    print("=" * 60)
    print(f"COD  5v5  → ID {cod.id}  → http://localhost:3000/tournaments/{cod.id}/manage")
    print(f"BGMI Squad → ID {bgmi.id} → http://localhost:3000/tournaments/{bgmi.id}/manage")
    print("\nBoth are 'ongoing' with all teams confirmed.")
    print("Round 1 is ready to configure from the manage page.")
