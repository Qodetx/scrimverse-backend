# Results Display UI - Frontend Component Locations

## 📍 Two Different UI Formats for Results

### 1️⃣ **OLD FORMAT - BGMI/Multi-Team Results (Multi-team BR)**
**Component:** [EliminatedTeamsModal.js](scrimverse-frontend/src/components/EliminatedTeamsModal.js)

**Structure:**
```
Group A Results:
├── ✓ 1 Qualified
├── ✕ 3 Eliminated
├── Qualified Teams Table
│  └── [Rank | Team Name | Total Points | Wins | Status]
└── Eliminated Teams Table
   └── [Rank | Team Name | Total Points | Wins | Status]
```

**Data it expects from API:**
```json
{
  "groups": [
    {
      "group_name": "Group A",
      "qualified_teams": [
        {
          "team_id": 1,
          "team_name": "Team A",
          "total_points": 57,
          "wins": 0,
          "rank": "#1",
          "status": "QUALIFIED"
        }
      ],
      "eliminated_teams": [
        {
          "team_id": 2,
          "team_name": "Team B",
          "total_points": 45,
          "wins": 0,
          "rank": "#2",
          "status": "ELIMINATED"
        }
      ],
      "qualified_count": 1,
      "eliminated_count": 3
    }
  ],
  "current_round": 1,
  "next_round": 2,
  "total_qualified": 2,
  "total_eliminated": 6
}
```

**File Location:** 
```
c:\Users\Kishan B M\scrimverse-frontend\src\components\EliminatedTeamsModal.js (lines 1-153)
```

---

### 2️⃣ **NEW FORMAT - 5v5 Head-to-Head Results (Valorant/COD)**
**Location:** [ManageTournament.js](scrimverse-frontend/src/pages/ManageTournament.js) (lines 1670-1730+)

**Structure:**
```
Group A Results (5v5 Head-to-Head):
├── Team A vs Team B
├── Match Results
│  ├── Match 1: Team A (10pts) vs Team B (5pts) → Team A wins
│  ├── Match 2: Team A (8pts) vs Team B (9pts) → Team B wins
│  └── Match 3: Team A (12pts) vs Team B (6pts) → Team A wins
├── Series Score: Team A 2 wins, Team B 1 win
└── Winner: Team A
```

**Data it expects from API:**
```json
{
  "groups": [
    {
      "format": "5v5_head_to_head",
      "standings": {
        "is_5v5": true,
        "team_a": {
          "team_id": 1,
          "team_name": "Team A",
          "match_wins": 2,
          "total_points": 30,
          "total_kills": 15
        },
        "team_b": {
          "team_id": 2,
          "team_name": "Team B",
          "match_wins": 1,
          "total_points": 20,
          "total_kills": 12
        },
        "match_results": [
          {
            "match_number": 1,
            "team_a_points": 10,
            "team_b_points": 5,
            "team_a_kills": 5,
            "team_b_kills": 2,
            "winner": "team_a",
            "status": "completed"
          }
        ],
        "series_score": {
          "team_a_wins": 2,
          "team_b_wins": 1
        },
        "group_winner": "team_a"
      }
    }
  ],
  "winner": {
    "team_id": 1,
    "team_name": "Team A"
  }
}
```

**File Location:** 
```
c:\Users\Kishan B M\scrimverse-frontend\src\pages\ManageTournament.js (lines 1670+)

Champion display: lines 1695-1740
Podium display: lines 1740-1860
```

---

## 🔧 API Endpoint to Wire

**Current Backend Endpoint:**
```
GET /api/tournaments/<tournament_id>/rounds/<round_number>/results/
```

**What it Returns:**
```python
# Mixes both formats in one response:
{
  "results": [...]  # For BGMI (list of teams)
  "groups": [       # For 5v5 (head-to-head match data)
    {
      "format": "multi_team" or "5v5_head_to_head",
      "standings": {...}
    }
  ]
}
```

---

## ⚠️ Current Issue

**The problem:** Both BGMI and 5v5 go through the SAME results endpoint, but they return different data structures:

| Tournament Type | Data Structure | Component | Issue |
|---|---|---|---|
| **BGMI (4v4 BR)** | `groups[].standings` = **LIST** | EliminatedTeamsModal | ✅ Works |
| **Valorant 5v5** | `groups[].standings` = **DICT** | ManageTournament | ✅ Works |

**But the code doesn't properly distinguish** → It tries to use list slicing on a dict → **KeyError**

---

## 🛠️ What You Need to Do

### Step 1: **Update Backend API Response**
Make `/api/tournaments/<id>/rounds/<round>/results/` return data WITH the `format` field clearly marked:

```python
{
  "groups": [
    {
      "group_name": "Group A",
      "format": "multi_team",  # ← Add this!
      "standings": [...]
    }
  ]
}
```

### Step 2: **Update Frontend Component**
In ManageTournament.js, check the `format` field:

```javascript
if (group.format === '5v5_head_to_head') {
  // Display 5v5 head-to-head results
} else {
  // Display EliminatedTeamsModal (BGMI style)
}
```

---

## 📁 File Summary

| File | Purpose | Lines | Format |
|---|---|---|---|
| **EliminatedTeamsModal.js** | BGMI multi-team results (old) | 1-153 | Table with Qualified/Eliminated |
| **ManageTournament.js** | 5v5 head-to-head results (new) | 1670+ | Head-to-head with match history |
| **groups_views.py** | Backend API response | - | Mixed `multi_team` + `5v5_head_to_head` |

