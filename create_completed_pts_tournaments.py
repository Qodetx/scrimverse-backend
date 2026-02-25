"""
Create 2 FULLY COMPLETED test tournaments for player kishanbm25@gmail.com (player1, id=2)
so that the PointsTableModal on the player dashboard shows real standings data.

Tournament 1: [PTS TEST] BGMI Squad — 2 rounds, 8 teams, 3 matches/group
Tournament 2: [PTS TEST] COD 5v5   — 2 rounds, 4 teams, 1 match/group

How it works:
  - player1's team (UserTeam000, id=95) is registered as captain in both tournaments
  - All Groups, Matches, and MatchScores are populated with realistic data
  - Tournaments are marked completed → all rounds unlocked in PointsTableModal
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.utils import timezone
from datetime import timedelta
from accounts.models import User, HostProfile, PlayerProfile, Team, TeamMember
from tournaments.models import (
    Tournament, TournamentRegistration, Group, Match, MatchScore, RoundScore,
)

now = timezone.now()

# ─── helpers ────────────────────────────────────────────────────────────────

def get_host():
    hp = HostProfile.objects.first()
    if not hp:
        raise RuntimeError("No HostProfile found – create a host user first.")
    return hp

def get_or_create_player(username, email):
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "user_type": "player"},
    )
    if _:
        user.set_password("test1234")
        user.save()
    pp, _ = PlayerProfile.objects.get_or_create(user=user)
    return user, pp

def get_or_create_team(name, captain_user):
    team, _ = Team.objects.get_or_create(name=name, defaults={"captain": captain_user})
    return team

def make_registration(tournament, player_profile, team_obj, team_name):
    reg, _ = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        player=player_profile,
        defaults={
            "team": team_obj,
            "team_name": team_name,
            "status": "confirmed",
        },
    )
    if not _:
        reg.status = "confirmed"
        reg.team_name = team_name
        reg.save()
    return reg

def make_simple_reg(tournament, player_profile, team_name):
    """Create a confirmed registration for a fake team (no real Team object)."""
    reg, _ = TournamentRegistration.objects.get_or_create(
        tournament=tournament,
        player=player_profile,
        defaults={
            "team": None,
            "team_name": team_name,
            "status": "confirmed",
        },
    )
    if not _:
        reg.status = "confirmed"
        reg.team_name = team_name
        reg.save()
    return reg

def create_bgmi_match_scores(match, ordered_regs, placement_pts_list, kills_list):
    """Create MatchScore for each team in placement order."""
    for rank, (reg, kills) in enumerate(zip(ordered_regs, kills_list)):
        pos_pts = placement_pts_list[rank] if rank < len(placement_pts_list) else 0
        total = pos_pts + kills
        MatchScore.objects.update_or_create(
            match=match,
            team=reg,
            defaults={
                "position_points": pos_pts,
                "kill_points": kills,
                "total_points": total,
                "wins": 1 if rank == 0 else 0,
            },
        )
    match.status = "completed"
    match.ended_at = now - timedelta(hours=1)
    match.save()

def create_cod_match_score(match, winner_reg, loser_reg):
    """Create MatchScore for COD 5v5 head-to-head (winner=3pts, loser=0pts)."""
    MatchScore.objects.update_or_create(
        match=match, team=winner_reg,
        defaults={"position_points": 3, "kill_points": 0, "total_points": 3, "wins": 1},
    )
    MatchScore.objects.update_or_create(
        match=match, team=loser_reg,
        defaults={"position_points": 0, "kill_points": 0, "total_points": 0, "wins": 0},
    )
    match.status = "completed"
    match.ended_at = now - timedelta(hours=1)
    match.save()

def create_group_with_matches(tournament, round_number, group_name, regs, matches_per_group, qualifying):
    """Create Group and Match objects for a given round."""
    group, _ = Group.objects.get_or_create(
        tournament=tournament,
        round_number=round_number,
        group_name=group_name,
        defaults={
            "qualifying_teams": qualifying,
            "status": "completed",
        },
    )
    if not _:
        group.status = "completed"
        group.qualifying_teams = qualifying
        group.save()

    for reg in regs:
        group.teams.add(reg)

    matches = []
    for m_num in range(1, matches_per_group + 1):
        match, _ = Match.objects.get_or_create(
            group=group,
            match_number=m_num,
            defaults={
                "match_id": f"ROOM{group.id}{m_num:02d}",
                "match_password": f"pass{group.id}{m_num}",
                "status": "pending",
                "scheduled_date": (now - timedelta(days=2)).date(),
                "scheduled_time": (now - timedelta(hours=6)).time(),
                "map_name": "Erangel" if "BGMI" in tournament.game_name else None,
            },
        )
        matches.append(match)

    return group, matches

# ─── BGMI PLACEMENT POINTS (standard) ───────────────────────────────────────
BGMI_PTS = [12, 9, 7, 5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0]

print("=" * 60)
print("Creating [PTS TEST] tournaments …")
print("=" * 60)

host = get_host()

# Player1 (kishanbm25@gmail.com)
_, player1_pp = get_or_create_player("player1", "kishanbm25@gmail.com")
team_userteam000 = get_or_create_team("UserTeam000", User.objects.get(username="player1"))

# ════════════════════════════════════════════════════════════════
# TOURNAMENT 1 — BGMI Squad (completed, 2 rounds)
# ════════════════════════════════════════════════════════════════
print("\n--- Creating BGMI tournament ---")

bgmi_t = Tournament.objects.create(
    host=host,
    event_mode="TOURNAMENT",
    title="[PTS TEST] BGMI Squad Championship",
    description="Test tournament for Points Table modal verification.",
    game_name="BGMI",
    game_mode="Squad",
    max_participants=8,
    current_participants=8,
    entry_fee=0,
    prize_pool=5000,
    rounds=[
        {"round": 1, "max_teams": 8, "qualifying_teams": 4},
        {"round": 2, "max_teams": 4, "qualifying_teams": 1},
    ],
    round_names={"2": "Finals"},
    current_round=2,
    round_status={"1": "completed", "2": "completed"},
    status="completed",
    tournament_date=(now - timedelta(days=3)).date(),
    tournament_time=(now - timedelta(hours=10)).time(),
    registration_start=now - timedelta(days=10),
    registration_end=now - timedelta(days=4),
    tournament_start=now - timedelta(days=3),
    tournament_end=now - timedelta(days=1),
)
print(f"  Created BGMI tournament: {bgmi_t.id} — {bgmi_t.title}")

# ── Opponent players/teams (7 fake opponents) ───────────────────
opp_names_bgmi = [
    ("bgmi_opp1", "bgmi_opp1@test.com", "Soul Snippers"),
    ("bgmi_opp2", "bgmi_opp2@test.com", "GodL Esports"),
    ("bgmi_opp3", "bgmi_opp3@test.com", "Revenant Esports"),
    ("bgmi_opp4", "bgmi_opp4@test.com", "OR Esports"),
    ("bgmi_opp5", "bgmi_opp5@test.com", "Marcos Gaming"),
    ("bgmi_opp6", "bgmi_opp6@test.com", "Team XO"),
    ("bgmi_opp7", "bgmi_opp7@test.com", "Global Esports"),
]

opp_regs_bgmi = []
for uname, email, tname in opp_names_bgmi:
    _, pp = get_or_create_player(uname, email)
    reg = make_simple_reg(bgmi_t, pp, tname)
    opp_regs_bgmi.append(reg)

# player1 registration
p1_bgmi_reg = make_registration(bgmi_t, player1_pp, team_userteam000, "UserTeam000")

# All 8 regs
all_bgmi_regs = [p1_bgmi_reg] + opp_regs_bgmi
# Grp A: player1 + opp0,1,2 (indices 0,1,2,3)  → p1 + Soul, GodL, Revenant
# Grp B: opp3,4,5,6 (indices 4,5,6,7)          → OR, Marcos, XO, Global
grp_a_r1 = all_bgmi_regs[:4]   # [p1, Soul, GodL, Revenant]
grp_b_r1 = all_bgmi_regs[4:]   # [OR, Marcos, XO, Global]

# ── Round 1 — Group A ─────────────────────────────────────────
grp_a, matches_a = create_group_with_matches(bgmi_t, 1, "Group A", grp_a_r1, 3, qualifying=2)

# Match 1: p1 wins, Soul 2nd, GodL 3rd, Revenant 4th
# kills: p1=6, Soul=4, GodL=3, Rev=1
create_bgmi_match_scores(matches_a[0],
    ordered_regs=[p1_bgmi_reg, opp_regs_bgmi[0], opp_regs_bgmi[1], opp_regs_bgmi[2]],
    placement_pts_list=BGMI_PTS,
    kills_list=[6, 4, 3, 1])

# Match 2: Soul wins, p1 2nd, Revenant 3rd, GodL 4th
create_bgmi_match_scores(matches_a[1],
    ordered_regs=[opp_regs_bgmi[0], p1_bgmi_reg, opp_regs_bgmi[2], opp_regs_bgmi[1]],
    placement_pts_list=BGMI_PTS,
    kills_list=[7, 5, 2, 1])

# Match 3: p1 wins again, GodL 2nd, Soul 3rd, Revenant 4th
create_bgmi_match_scores(matches_a[2],
    ordered_regs=[p1_bgmi_reg, opp_regs_bgmi[1], opp_regs_bgmi[0], opp_regs_bgmi[2]],
    placement_pts_list=BGMI_PTS,
    kills_list=[8, 5, 3, 0])

print(f"  BGMI R1 Group A: 3 matches scored ✓")

# ── Round 1 — Group B ─────────────────────────────────────────
grp_b, matches_b = create_group_with_matches(bgmi_t, 1, "Group B", grp_b_r1, 3, qualifying=2)

# Match 1: Marcos wins
create_bgmi_match_scores(matches_b[0],
    ordered_regs=[opp_regs_bgmi[4], opp_regs_bgmi[3], opp_regs_bgmi[5], opp_regs_bgmi[6]],
    placement_pts_list=BGMI_PTS,
    kills_list=[5, 3, 4, 2])

# Match 2: OR wins
create_bgmi_match_scores(matches_b[1],
    ordered_regs=[opp_regs_bgmi[3], opp_regs_bgmi[6], opp_regs_bgmi[4], opp_regs_bgmi[5]],
    placement_pts_list=BGMI_PTS,
    kills_list=[6, 4, 3, 1])

# Match 3: XO wins
create_bgmi_match_scores(matches_b[2],
    ordered_regs=[opp_regs_bgmi[5], opp_regs_bgmi[4], opp_regs_bgmi[3], opp_regs_bgmi[6]],
    placement_pts_list=BGMI_PTS,
    kills_list=[4, 5, 2, 1])

print(f"  BGMI R1 Group B: 3 matches scored ✓")

# ── Round 2 — Grand Final (top 2 from each group) ────────────────
# Group A top 2: p1 (26+8=34 total), Soul (9+5+3=17+kills ~25 total)
# Group B top 2: Marcos, OR
final_regs = [p1_bgmi_reg, opp_regs_bgmi[0], opp_regs_bgmi[4], opp_regs_bgmi[3]]
grp_final, matches_f = create_group_with_matches(bgmi_t, 2, "Grand Final", final_regs, 3, qualifying=1)

# Final Match 1: p1 crushes
create_bgmi_match_scores(matches_f[0],
    ordered_regs=[p1_bgmi_reg, opp_regs_bgmi[4], opp_regs_bgmi[0], opp_regs_bgmi[3]],
    placement_pts_list=BGMI_PTS,
    kills_list=[10, 4, 3, 2])

# Final Match 2: Soul wins
create_bgmi_match_scores(matches_f[1],
    ordered_regs=[opp_regs_bgmi[0], p1_bgmi_reg, opp_regs_bgmi[3], opp_regs_bgmi[4]],
    placement_pts_list=BGMI_PTS,
    kills_list=[6, 8, 2, 1])

# Final Match 3: p1 wins championship
create_bgmi_match_scores(matches_f[2],
    ordered_regs=[p1_bgmi_reg, opp_regs_bgmi[0], opp_regs_bgmi[4], opp_regs_bgmi[3]],
    placement_pts_list=BGMI_PTS,
    kills_list=[9, 5, 3, 1])

print(f"  BGMI R2 Grand Final: 3 matches scored ✓")

# ── Update tournament state ───────────────────────────────────
bgmi_t.selected_teams = {
    "1": [p1_bgmi_reg.id, opp_regs_bgmi[0].id, opp_regs_bgmi[4].id, opp_regs_bgmi[3].id],
}
bgmi_t.winners = {"champion": {"reg_id": p1_bgmi_reg.id, "team_name": "UserTeam000"}}
bgmi_t.save()
print(f"  BGMI tournament state updated ✓")


# ════════════════════════════════════════════════════════════════
# TOURNAMENT 2 — COD 5v5 (completed, 2 rounds)
# ════════════════════════════════════════════════════════════════
print("\n--- Creating COD 5v5 tournament ---")

cod_t = Tournament.objects.create(
    host=host,
    event_mode="TOURNAMENT",
    title="[PTS TEST] COD 5v5 Invitational",
    description="Test tournament for Points Table modal verification.",
    game_name="COD",
    game_mode="5v5",
    max_participants=4,
    current_participants=4,
    entry_fee=0,
    prize_pool=3000,
    rounds=[
        {"round": 1, "max_teams": 4, "qualifying_teams": 2},
        {"round": 2, "max_teams": 2, "qualifying_teams": 1},
    ],
    round_names={"2": "Grand Final"},
    current_round=2,
    round_status={"1": "completed", "2": "completed"},
    status="completed",
    tournament_date=(now - timedelta(days=2)).date(),
    tournament_time=(now - timedelta(hours=8)).time(),
    registration_start=now - timedelta(days=8),
    registration_end=now - timedelta(days=3),
    tournament_start=now - timedelta(days=2),
    tournament_end=now - timedelta(days=1),
)
print(f"  Created COD tournament: {cod_t.id} — {cod_t.title}")

# ── Opponent players/teams (3 fake opponents) ───────────────────
opp_names_cod = [
    ("cod_opp1", "cod_opp1@test.com", "FaZe Clan"),
    ("cod_opp2", "cod_opp2@test.com", "Natus Vincere"),
    ("cod_opp3", "cod_opp3@test.com", "Team Liquid"),
]

opp_regs_cod = []
for uname, email, tname in opp_names_cod:
    _, pp = get_or_create_player(uname, email)
    reg = make_simple_reg(cod_t, pp, tname)
    opp_regs_cod.append(reg)

# player1 registration
p1_cod_reg = make_registration(cod_t, player1_pp, team_userteam000, "UserTeam000")

# ── Round 1: 2 lobbies ────────────────────────────────────────
# Lobby 1: player1 vs FaZe Clan → player1 wins
grp_r1_lobby1, matches_r1l1 = create_group_with_matches(
    cod_t, 1, "Lobby 1", [p1_cod_reg, opp_regs_cod[0]], 1, qualifying=1
)
create_cod_match_score(matches_r1l1[0], winner_reg=p1_cod_reg, loser_reg=opp_regs_cod[0])
print(f"  COD R1 Lobby 1: player1 def FaZe ✓")

# Lobby 2: Natus Vincere vs Team Liquid → NaVi wins
grp_r1_lobby2, matches_r1l2 = create_group_with_matches(
    cod_t, 1, "Lobby 2", [opp_regs_cod[1], opp_regs_cod[2]], 1, qualifying=1
)
create_cod_match_score(matches_r1l2[0], winner_reg=opp_regs_cod[1], loser_reg=opp_regs_cod[2])
print(f"  COD R1 Lobby 2: NaVi def Team Liquid ✓")

# ── Round 2: Grand Final ──────────────────────────────────────
grp_r2, matches_r2 = create_group_with_matches(
    cod_t, 2, "Grand Final", [p1_cod_reg, opp_regs_cod[1]], 1, qualifying=1
)
create_cod_match_score(matches_r2[0], winner_reg=p1_cod_reg, loser_reg=opp_regs_cod[1])
print(f"  COD R2 Grand Final: player1 def NaVi ✓")

# ── Update tournament state ───────────────────────────────────
cod_t.selected_teams = {
    "1": [p1_cod_reg.id, opp_regs_cod[1].id],
}
cod_t.winners = {"champion": {"reg_id": p1_cod_reg.id, "team_name": "UserTeam000"}}
cod_t.save()
print(f"  COD tournament state updated ✓")

# ════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("DONE — both tournaments created successfully!")
print("=" * 60)
print(f"\nBGMI Tournament ID: {bgmi_t.id}")
print(f"  player1 reg ID:    {p1_bgmi_reg.id}")
print(f"  Groups R1: {Group.objects.filter(tournament=bgmi_t, round_number=1).count()}")
print(f"  Groups R2: {Group.objects.filter(tournament=bgmi_t, round_number=2).count()}")
print(f"  Total matches: {Match.objects.filter(group__tournament=bgmi_t).count()}")
print(f"  Total scores:  {MatchScore.objects.filter(match__group__tournament=bgmi_t).count()}")

print(f"\nCOD Tournament ID: {cod_t.id}")
print(f"  player1 reg ID:    {p1_cod_reg.id}")
print(f"  Groups R1: {Group.objects.filter(tournament=cod_t, round_number=1).count()}")
print(f"  Groups R2: {Group.objects.filter(tournament=cod_t, round_number=2).count()}")
print(f"  Total matches: {Match.objects.filter(group__tournament=cod_t).count()}")
print(f"  Total scores:  {MatchScore.objects.filter(match__group__tournament=cod_t).count()}")

print(f"\nPlayer1 can view at:")
print(f"  BGMI → /tournaments/{bgmi_t.id}/manage  (Points Table button)")
print(f"  COD  → /tournaments/{cod_t.id}/manage   (Points Table button)")
print(f"\nOR on the Player Dashboard (player1 must be logged in)")
print(f"  localhost:3000/player/dashboard")
