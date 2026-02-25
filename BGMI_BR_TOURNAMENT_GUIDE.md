# BGMI Squad (4v4) BR Tournament - Complete Step-by-Step Guide

## Overview
This guide documents how a BGMI Squad Battle Royale tournament works in Scrimverse, from creation through victory. Unlike 5v5 head-to-head tournaments (where 2 teams compete 1v1), BR tournaments have all teams in a group competing simultaneously in each match.

---

## Step 1: Host Creates Tournament

### What the Host Does
The tournament host (creator) goes to the tournament creation page and fills in:
- **Tournament Title**: e.g., "BGMI Squad Test Tournament"
- **Game**: BGMI
- **Format**: Squad (4 players per team)
- **Prize Pool**: ₹50,000
- **Entry Fee**: ₹0.00
- **Start Date**: Feb 23, 2026
- **Max Participants**: 12 teams
- **Round Structure**: Configure which rounds exist and how many teams qualify from each

### What Happens (Backend Summary)
A **Tournament** record is created in the database with:
- Tournament details (title, game, format, prize pool)
- **Rounds configuration**: 
  - Round 1: 12 teams enter, 6 qualify
  - Round 2: 6 teams enter, 3 qualify
  - Round 3: 3 teams enter, 1 wins
- Status set to "created" (waiting for registrations)
- Host linked as tournament owner

---

## Step 2: Players/Teams Register for Tournament

### What Teams/Players Do
A team captain goes to the tournament details page and clicks **Register**.

They can:
- Register an **existing team** they own, OR
- Create a **new temporary team** just for this tournament

For our example: **12 teams register** for the BGMI tournament

### What Happens (Backend Summary)
For each team that registers:
1. If new team created → **Team** record added (name, captain, is_temporary=True)
2. **TournamentRegistration** record created linking:
   - The tournament
   - The player (team captain)
   - The team
   - Status: "confirmed" (team is in tournament)

After 12 registrations → Tournament shows **12/12 teams registered** and is ready to start

---

## Step 3: Host Initializes Round 1 (Qualifiers)

### What the Host Does
The host clicks **INITIALIZE MATCHES** on the tournament manage page.

A modal appears: **Configure Qualifiers**

The host enters:
- **Teams per group**: 6
- **Qualifying per group**: 3
- **Matches per group**: 4

This means: "Create 2 groups of 6 teams each, play 4 matches in each group, top 3 from each group (6 total) advance to Round 2"

Preview shows:
- Total Teams: 12
- Groups: 2 (12÷6=2)
- Teams per Group: 6
- Qualifying: 3 per group × 2 groups = 6 advancing

Host clicks **Confirm & Start Round**.

### What Happens in the Backend

#### A. Groups Created
```python
# For round 1, get all confirmed registrations
teams = TournamentRegistration.objects.filter(
    tournament=tournament, 
    status="confirmed"
)  # 12 teams

# Calculate distribution: 2 groups of 6
num_groups = 2
teams_distribution = [6, 6]

# Create Group objects
Group.objects.create(
    tournament=tournament,
    round_number=1,
    group_name="Group A",
    qualifying_teams=3,  # Top 3 will advance
)

Group.objects.create(
    tournament=tournament,
    round_number=1,
    group_name="Group B",
    qualifying_teams=3,
)

# Shuffle teams randomly and assign to groups
# Group A gets teams 1-6
# Group B gets teams 7-12
```

#### B. Matches Created for Each Group
```python
# For each group, create 4 match records
for match_num in [1, 2, 3, 4]:
    Match.objects.create(
        group=group_a,
        match_number=match_num,
        status="waiting",  # Not started yet
    )
    # Same for Group B
```

Result:
- Group A: 4 matches (Match 1, 2, 3, 4)
- Group B: 4 matches (Match 1, 2, 3, 4)
- All 8 matches in "waiting" state

#### C. Tournament State Updated
```python
tournament.current_round = 1  # Now in Round 1
tournament.save()
```

### Frontend Display
The Manage Tournament page now shows:
```
Groups Management
├── GROUP A (LIVE)
│   └── 6 participants
│       Battle Progress: 0/4
├── GROUP B (LIVE)
│   └── 6 participants
│       Battle Progress: 0/4
```

Users can click on "GROUP A" to see the group details and start entering match results.

### Why This Matters
- Groups define which teams compete together in matches
- `qualifying_teams=3` is stored on the Group, used later to determine qualifiers
- Matches are the unit of play in BR — each match is one squad match where all 6 teams participate
- Teams are randomly shuffled to ensure fairness

---

## Step 4: Teams Play Matches & Enter Results

### What Happens in the UI
Host/scorekeeper clicks on **GROUP A** card.

Shows:
- **Match 1** (0/6 button, waiting state)
- **Match 2** (0/6 button, waiting)
- **Match 3** (0/6 button, waiting)
- **Match 4** (0/6 button, waiting)

For **Match 1**:
1. Click **START MATCH** → match status becomes "ongoing"
2. Teams play in real Battle Royale squad match (real game or simulated)
3. Click **END MATCH** → match state becomes "completed"
4. Click **ENTER POINTS** → modal opens

### Points Entry Modal
The modal shows all 6 teams in Group A with fields:

| TEAM NAME | POSITION PTS | KILL PTS | TOTAL PTS |
|---|---|---|---|
| Stalwart Esports | [1] | [12] | 13 |
| Team Mayhem | [2] | [8] | 10 |
| Team Insane | [3] | [10] | 13 |
| OR Esports | [4] | [5] | 9 |
| GodL Esports | [5] | [6] | 11 |
| Soul Snippers | [6] | [3] | 9 |

**Position Points** = Placement rank (1st=1 point, 2nd=2, ..., 6th=6)
**Kill Points** = Number of enemy squads eliminated
**Total Points** = Position Pts + Kill Pts (auto-calculated)

### What Happens in the Backend

When host clicks **SUBMIT POINTS**:

```python
# For each team in the match
MatchScore.objects.create(
    match=match_1,
    team=stalwart_esports_registration,
    position_points=1,
    kill_points=12,
    wins=0,  # Not used in BR (used in 5v5)
)

MatchScore.objects.create(
    match=match_1,
    team=team_mayhem_registration,
    position_points=2,
    kill_points=8,
    wins=0,
)
# ... etc for all 6 teams
```

**MatchScore Table grows:**
- Match 1 now has 6 MatchScore records (one per team)
- Each record stores the position and kill points for that team in that match

### Repeat for All Matches
This process repeats for:
- Group A: Match 1, Match 2, Match 3, Match 4 (4 times) = 24 MatchScore records for Group A
- Group B: Match 1, Match 2, Match 3, Match 4 (4 times) = 24 MatchScore records for Group B
- **Total: 48 MatchScore records** (6 teams × 4 matches × 2 groups)

### Why This Matters
- Each team accumulates points across 4 matches
- MatchScore is the raw data; leaderboard is calculated from it
- BR scoring allows wins and losses to vary match-to-match (unlike 5v5 where winning/losing a series is binary)

---

## Step 5: Determine Qualifiers (Group Leaderboard)

### What Happens Behind the Scenes
After all 4 matches in a group are completed, the system calculates standings:

```python
def calculate_group_standings(group):
    standings = []
    
    for team in group.teams.all():
        # Sum all points for this team across all matches in the group
        scores = MatchScore.objects.filter(
            match__group=group,
            team=team
        ).aggregate(
            total_pp=Sum("position_points"),
            total_kp=Sum("kill_points"),
        )
        
        total_points = (scores["total_pp"] or 0) + (scores["total_kp"] or 0)
        
        standings.append({
            "team_name": team.team_name,
            "total_points": total_points,
            "position_points": scores["total_pp"],
            "kill_points": scores["total_kp"],
        })
    
    # Sort by total points (descending)
    standings.sort(key=lambda x: -x["total_points"])
    return standings
```

### Example: Group A Leaderboard After 4 Matches

| Rank | Team Name | Position Pts | Kill Pts | Total Pts |
|---|---|---|---|---|
| 1 | Stalwart Esports | 8 | 43 | 51 |
| 2 | Team Insane | 12 | 36 | 48 |
| 3 | OR Esports | 18 | 26 | 44 |
| 4 | Team Mayhem | 16 | 21 | 37 |
| 5 | Gladiators Esports | 22 | 14 | 36 |
| 6 | Soul Snippers | 24 | 11 | 35 |

**Top 3 qualify** (because `qualifying_teams=3`):
- ✅ Stalwart Esports (51)
- ✅ Team Insane (48)
- ✅ OR Esports (44)

**Bottom 3 eliminated**:
- ❌ Team Mayhem (37)
- ❌ Gladiators Esports (36)
- ❌ Soul Snippers (35)

### What the Host Sees
After completing all matches, the "Qualifiers Complete - Results" modal appears showing:

```
✓ 3 Qualified teams
✗ 3 Eliminated teams

Group A
✓ 3 Qualified
✗ 3 Eliminated
  QUALIFIED TEAMS
  1. Stalwart Esports (51 pts)
  2. Team Insane (48 pts)
  3. OR Esports (44 pts)
  
  ELIMINATED TEAMS
  4. Team Mayhem (37 pts)
  5. Gladiators Esports (36 pts)
  6. Soul Snippers (35 pts)
```

### Backend: Store Qualified Team IDs
```python
# After calculating qualified teams from both groups
tournament.selected_teams["1"] = [
    stalwart_registration.id,
    team_insane_registration.id,
    or_esports_registration.id,
    velocity_gaming_registration.id,   # From Group B
    team_ind_registration.id,           # From Group B
    marcos_gaming_registration.id,      # From Group B
]

tournament.round_status["1"] = "completed"
tournament.current_round = 2  # Move to Round 2

tournament.save()
```

### Why This Matters
- Qualification is automatic based on total points
- `selected_teams` stores which registrations advance (by registration ID, not team object)
- `current_round` is updated to 2, blocking further Round 1 changes
- Tied teams lose tiebreakers (kills, then alphabetical) — system can break ties consistently

---

## Step 6: Configure Round 2 (Semi-Finals)

### What the Host Does
After all Group A and Group B results are finalized, the page shows:

```
→ NEXT SECTOR: SEMI-FINALS
```

Host clicks it. The **Qualifiers Complete - Results** modal appears showing all 6 qualifiers. Host clicks **Proceed to Configure Semi-Finals**.

The **Configure Semi-Finals** modal appears:

- **Teams per group**: [6] (all 6 qualifiers)
- **Qualifying per group**: [3] (top 3 advance to Grand Finals)
- **Matches per group**: [4]

Preview:
```
Total Teams: 6
Groups: 1
Teams per Group: 6
Matches per Group: 4
Qualifying Teams: 3
```

Host clicks **Confirm & Start Round**.

### Backend Process (Same as Round 1)
```python
# 1. Get qualified teams from selected_teams["1"]
qualified_reg_ids = tournament.selected_teams["1"]
teams = TournamentRegistration.objects.filter(id__in=qualified_reg_ids)  # 6 teams

# 2. Create 1 group (because 6 ÷ 6 = 1 group)
Group.objects.create(
    tournament=tournament,
    round_number=2,
    group_name="Group A",
    qualifying_teams=3,
)

# 3. Create 4 matches in that group
for match_num in [1, 2, 3, 4]:
    Match.objects.create(group=group, match_number=match_num)

# 4. Update tournament state
tournament.current_round = 2
tournament.save()
```

### Why This Matters
- Single large group with all 6 teams
- Same points-based qualification (top 3 advance)
- Smaller pool means more competitive matches

---

## Step 7-8: Round 2 Matches & Qualification to Grand Finals

**Exactly the same process as Steps 4-5:**

1. Enter points for all 4 matches
2. System calculates leaderboard (sum of 4 matches)
3. Top 3 teams qualify for Grand Finals
4. Selected teams are stored in `tournament.selected_teams["2"]`
5. `tournament.current_round = 3`

Example finals qualifiers:
- Stalwart Esports (46 pts)
- Team IND (46 pts)
- Marcos Gaming (45 pts)

---

## Step 9: Configure Grand Finals

### What the Host Does
After Semi-Finals results, click **→ NEXT SECTOR: GRAND FINALS**.

The **Configure Grand Finals** modal appears with fields locked (because `isFinalRound=True`):
- **Teams per group**: 3 (disabled, auto-set)
- **Qualifying per group**: 1 (disabled, auto-set)
- **Matches per group**: [4] (editable)

Preview:
```
Total Teams: 3
Groups: 1
Teams per Group: 3
Matches per Group: 4
Qualifying Teams: 1
```

The modal also shows:
```
🏆 Final Round Configuration
All remaining teams will compete in a single group. 
Only the number of matches can be configured.
```

Host clicks **Confirm & Start Round**.

### Backend
```python
# Get 3 qualified teams
teams = TournamentRegistration.objects.filter(
    id__in=tournament.selected_teams["2"]
)  # 3 teams

# Create 1 group with 3 teams
Group.objects.create(
    tournament=tournament,
    round_number=3,
    group_name="Group A",
    qualifying_teams=1,  # Only 1 winner
)

# Create 4 matches
for match_num in [1, 2, 3, 4]:
    Match.objects.create(group=group, match_number=match_num)

tournament.current_round = 3
```

### Why This Differs from Semis
- `isFinalRound=True` is set because `current_round == tournament.rounds.length` (3 == 3)
- RoundConfigModal locks teams_per_group and qualifying_per_group (can't change final bracket)
- Only matches_per_group is editable

---

## Step 10: Grand Finals Matches

**Same process as Rounds 1-2:**

1. Enter points for all 4 matches (3 teams, 4 matches = 12 MatchScore records)
2. Calculate final leaderboard

### Final Leaderboard Example
| Rank | Team | Pts |
|---|---|---|
| 1 | **Stalwart Esports** | 36 |
| 2 | Team IND | 30 |
| 3 | Marcos Gaming | 28 |

---

## Step 11: Victory Ceremony & Tournament Conclusion

### Automatic Trigger
After the final match scores are entered, the system:

1. **Calculates the winner** (highest total points):
   ```python
   winner = standings[0]  # Stalwart Esports
   winner_registration = winner["registration"]
   tournament_obj.winner = winner_registration
   ```

2. **Updates tournament status**:
   ```python
   tournament.is_active = False
   tournament.status = "concluded"
   tournament.save()
   ```

3. **Displays Victory Page**:
   ```
   TOURNAMENT CONCLUDED
   
   Victory Ceremony
   Tournament Concluded
   
   ⭐ CHAMPION
   🏅 Stalwart Esports
      36 PTS
   
   Tournament Stats:
   - Rounds: 3
   - Teams: 12
   - Prize Pool: ₹50,000
   - Winner: Stalwart Esports
   ```

### What Happened
- Teams competed in BR format across 3 rounds
- Points accumulated through placement and kills
- No bye teams (BR mode distributes evenly into groups)
- Winner determined by highest cumulative points

---

## Key Differences: BR vs 5v5 Head-to-Head

| Aspect | BR (BGMI Squad) | 5v5 (Valorant/COD) |
|---|---|---|
| **Group Size** | Multi-team (6 per group typical) | Exactly 2 teams (head-to-head) |
| **Scoring** | Position + Kill points | Map wins (1 point per map won) |
| **Advancement** | Top N teams by points | Winner of series (BO1/BO2/BO3) |
| **Matches** | All teams play together | 1v1 lobby match |
| **Qualifiers** | Automatic top-N by points | Winner/Runner-up of lobby |
| **Bye Teams** | None (even distribution) | Possible if odd teams |
| **Config Fields** | teams/group, qual/group, matches | Best-of (1/2/3/4) |

---

## Database Schema (Simplified)

```
Tournament (ID: 68)
├── game_name: "BGMI"
├── game_mode: "Squad"
├── current_round: 3 (now finished)
├── selected_teams: {
│   "1": [reg_id1, reg_id2, ...],  # 6 qualifiers from Round 1
│   "2": [reg_id3, reg_id4, ...]   # 3 qualifiers from Round 2
│ }
├── round_status: {"1": "completed", "2": "completed", "3": "completed"}
│
├── TournamentRegistration (12 total)
│ ├── ID-1: Stalwart Esports, status: confirmed
│ ├── ID-2: Team Mayhem, status: confirmed
│ └── ...
│
├── Group (3 total - 2 in R1, 1 in R2, 1 in R3)
│ ├── Round 1, Group A (6 teams)
│ │  ├── Match 1
│ │  │  ├── MatchScore: Stalwart → pos:1, kills:12
│ │  │  ├── MatchScore: Team Mayhem → pos:2, kills:8
│ │  │  └── ... (4 more teams)
│ │  ├── Match 2
│ │  └── Match 3, 4 (same structure)
│ │
│ ├── Round 1, Group B (6 teams)
│ │  └── ... (4 matches, 6 teams each)
│ │
│ ├── Round 2, Group A (6 teams)
│ │  └── ... (4 matches, 6 teams each)
│ │
│ └── Round 3, Group A (3 teams - FINALS)
│    └── ... (4 matches, 3 teams each)
```

---

## Summary Timeline

1. **Host creates tournament** → Tournament object + round structure
2. **12 teams register** → 12 TournamentRegistration records
3. **Host initializes Round 1** → 2 groups, 4 matches each
4. **Teams enter match results** → 48 MatchScore records (6 teams × 4 matches × 2 groups)
5. **System calculates qualifiers** → Top 3 from each group (6 total)
6. **Round 2 configured** → 1 group of 6, 4 matches
7. **Round 2 results entered** → 24 MatchScore records
8. **Qualifiers to finals** → Top 3 from Round 2
9. **Grand Finals configured** → 1 group of 3, 4 matches
10. **Finals results entered** → 12 MatchScore records
11. **Winner declared** → Stalwart Esports (36 pts)
12. **Tournament concluded** → Victory ceremony displayed

---

**End of Step 1-2 Documentation**

Next steps to document:
- Step 3-6: Round configuration and match flow
- Step 7-11: Results, qualification, and finals
- Advanced topics: Tie-breaking, payment flows, team management
