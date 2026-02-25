"""
Complete all 6 matches in tournament 78 (BGMI Squad Live Test) Round 1.
- Enters realistic placement + kill points for all 16 teams across 6 matches
- Marks all matches as completed
- Marks Group A as completed
- Updates round_status and selected_teams on the Tournament
- Determines which team qualifies for Round 2 (qualifying_teams=1 per group)
"""
import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'scrimverse.settings'
django.setup()

from django.utils import timezone
from django.db.models import Sum
from tournaments.models import (
    Tournament, TournamentRegistration, Match, Group, MatchScore, RoundScore
)

t = Tournament.objects.get(id=78)
g = Group.objects.get(tournament=t, round_number=1)

# All 16 registrations in group order
regs = list(g.teams.all())
reg_map = {r.id: r for r in regs}

# Team names for quick reference
def tname(r): return r.team.name

print(f"Tournament: {t.title}")
print(f"Group: {g.group_name} | Teams: {len(regs)} | q_teams: {g.qualifying_teams}")
print()

# ── Realistic BGMI placement + kill scores for 6 matches ──────────────────────
# Format: [(reg_index, position_points, kill_points), ...]  per match
# Placement points follow BGMI standard: 1st=12,2nd=9,3rd=7,4th=5,5th=4,6th=3,7th=2,8th=1,9-16=0
# Kills: 1pt each, realistic range 0-8
# Different teams win different matches to vary the standings

PLACEMENT_PTS = [12, 9, 7, 5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0]

# (match_number, finishing_order_reg_idx, kills_per_team)
# finishing_order = index into regs[] list, first = winner
match_data = [
    # Match 1 — Soul Snippers wins
    {
        "order": [0,  4,  8, 12,  2,  6, 10, 14,  1,  5,  9, 13,  3,  7, 11, 15],
        "kills": [6,  4,  5,  3,  2,  4,  1,  3,  2,  3,  1,  0,  4,  2,  1,  0],
    },
    # Match 2 — GodL Esports wins (idx 1)
    {
        "order": [1,  7, 13,  5, 11,  3,  9, 15,  0,  6, 12,  4, 10,  2,  8, 14],
        "kills": [8,  5,  3,  4,  2,  3,  1,  2,  3,  2,  1,  3,  1,  2,  0,  1],
    },
    # Match 3 — Team XO wins (idx 4)
    {
        "order": [4,  0, 10,  6, 14,  2,  8, 12,  1,  5,  9, 13,  3,  7, 11, 15],
        "kills": [7,  3,  4,  2,  5,  3,  2,  1,  4,  2,  1,  2,  3,  1,  0,  1],
    },
    # Match 4 — Gladiators Esports wins (idx 8)
    {
        "order": [8,  2,  6, 14,  0, 10,  4, 12,  1,  5,  9, 13,  3,  7, 11, 15],
        "kills": [5,  4,  3,  3,  6,  2,  4,  1,  2,  3,  1,  2,  3,  1,  1,  0],
    },
    # Match 5 — Soul Snippers wins again (idx 0)
    {
        "order": [0,  8,  4, 12,  2,  6, 10, 14,  1,  5,  9, 13,  3,  7, 11, 15],
        "kills": [4,  6,  3,  2,  5,  3,  2,  1,  4,  2,  1,  2,  3,  1,  0,  1],
    },
    # Match 6 — GodL Esports wins (idx 1)
    {
        "order": [1,  0,  7, 13,  5, 11,  3,  9, 15,  4,  6, 12,  8, 10,  2, 14],
        "kills": [6,  5,  4,  3,  3,  2,  4,  1,  2,  3,  2,  1,  3,  1,  2,  0],
    },
]

matches = list(Match.objects.filter(group=g).order_by('match_number'))

assert len(matches) == 6, f"Expected 6 matches, got {len(matches)}"
assert len(regs) == 16, f"Expected 16 teams, got {len(regs)}"

total_scores = {r.id: 0 for r in regs}  # accumulate total for RoundScore

for i, (match, mdata) in enumerate(zip(matches, match_data), 1):
    order = mdata["order"]   # indexes into regs[]
    kills = mdata["kills"]
    print(f"Match {i} (ID={match.id}):")
    for rank, (reg_idx, kill) in enumerate(zip(order, kills)):
        reg = regs[reg_idx]
        pos_pts = PLACEMENT_PTS[rank]
        kill_pts = kill
        total_pts = pos_pts + kill_pts
        score, created = MatchScore.objects.update_or_create(
            match=match,
            team=reg,
            defaults={
                "position_points": pos_pts,
                "kill_points": kill_pts,
                "total_points": total_pts,
                "wins": 1 if rank == 0 else 0,
            }
        )
        total_scores[reg.id] += total_pts
        if rank < 3:
            print(f"  #{rank+1} {tname(reg):25s} pos={pos_pts:2d} kills={kill_pts} total={total_pts}")
    print(f"  ... (all 16 teams scored)")

    # Mark match completed
    match.status = "completed"
    if not match.started_at:
        match.started_at = timezone.now()
    match.ended_at = timezone.now()
    match.save(update_fields=["status", "started_at", "ended_at"])
    print(f"  ✅ Match {i} marked COMPLETED\n")

# ── Mark Group as completed ────────────────────────────────────────────────────
g.status = "completed"
g.save(update_fields=["status"])
print("✅ Group A marked COMPLETED")

# ── Create/update RoundScore for each team ─────────────────────────────────────
for reg in regs:
    rs, _ = RoundScore.objects.update_or_create(
        tournament=t,
        round_number=1,
        team=reg,
        defaults={
            "position_points": total_scores[reg.id] // 2,  # approx split
            "kill_points": total_scores[reg.id] - (total_scores[reg.id] // 2),
        }
    )
print("✅ RoundScore updated for all 16 teams")

# ── Determine qualifier(s) based on group's qualifying_teams ──────────────────
team_totals = sorted(total_scores.items(), key=lambda x: x[1], reverse=True)
qualifying_count = g.qualifying_teams  # = 1

print(f"\n📊 Final standings (top {qualifying_count + 3} shown):")
for rank, (reg_id, pts) in enumerate(team_totals[:qualifying_count + 3], 1):
    reg = reg_map[reg_id]
    marker = "⭐ QUALIFIES" if rank <= qualifying_count else ""
    print(f"  #{rank:2d} {tname(reg):25s} {pts:3d}pts {marker}")

qualified_reg_ids = [reg_id for reg_id, _ in team_totals[:qualifying_count]]

# ── Update tournament round_status and selected_teams ─────────────────────────
round_status = t.round_status or {}
round_status["1"] = {"status": "completed"}
t.round_status = round_status

selected_teams = t.selected_teams or {}
selected_teams["1"] = qualified_reg_ids
t.selected_teams = selected_teams

t.save(update_fields=["round_status", "selected_teams"])

print(f"\n✅ Tournament round_status['1'] = completed")
print(f"✅ selected_teams['1'] = {qualified_reg_ids} ({tname(reg_map[qualified_reg_ids[0]])})")
print(f"\n🎉 Round 1 complete! You can now start Round 2 (Semi-Finals).")
print(f"👉 http://localhost:3000/tournaments/{t.id}/manage")
