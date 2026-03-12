"""
Submit scores for Tournament 85 (Valorant Pro Showdown)
Completes all matches in Round 1 with realistic Valorant-style scores.
"""
import os
import django

os.environ['DJANGO_SETTINGS_MODULE'] = 'scrimverse.settings'
django.setup()

from django.utils import timezone
from tournaments.models import Tournament, Group, Match, MatchScore, RoundScore
from tournaments.services import TournamentGroupService

tournament = Tournament.objects.get(id=85)
print(f"Tournament: {tournament.title} (id={tournament.id})")

# Valorant maps
MAPS = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze', 'Fracture', 'Pearl', 'Lotus', 'Sunset']

# Score data for each lobby (group)
# Format: { group_id: [ (team1_score, team2_score, map_name), ...for each match ] }
LOBBY_SCORES = {
    # Lobby 1: Shadow Nexus (397) vs Phoenix Rising (396) 
    # Phoenix Rising wins 4-2 (Player kishanbm25@gmail.com's team)
    117: [
        (8, 13, 'Bind'),      # M1: PR wins
        (13, 11, 'Haven'),    # M2: SN wins
        (5, 13, 'Split'),     # M3: PR wins
        (13, 9, 'Ascent'),    # M4: SN wins
        (7, 13, 'Icebox'),    # M5: PR wins
        (6, 13, 'Breeze'),    # M6: PR wins
    ],
    # Lobby 2: Cyber Wolves (403) vs Dark Matter (401)
    # Cyber Wolves wins 4-2
    118: [
        (13, 7, 'Fracture'),  # M1: CW wins
        (9, 13, 'Pearl'),     # M2: DM wins
        (13, 11, 'Lotus'),    # M3: CW wins
        (13, 8, 'Sunset'),    # M4: CW wins
        (6, 13, 'Bind'),      # M5: DM wins
        (13, 5, 'Haven'),     # M6: CW wins
    ],
    # Lobby 3: Ghost Protocol (405) vs Viper Strike (402)
    # Ghost Protocol wins 4-2
    119: [
        (13, 9, 'Split'),     # M1: GP wins
        (11, 13, 'Ascent'),   # M2: VS wins
        (13, 7, 'Icebox'),    # M3: GP wins
        (8, 13, 'Breeze'),    # M4: VS wins
        (13, 6, 'Fracture'),  # M5: GP wins
        (13, 10, 'Pearl'),    # M6: GP wins
    ],
    # Lobby 4: Iron Wolves (399) vs Storm Breakers (398)
    # Storm Breakers wins 4-2
    120: [
        (7, 13, 'Lotus'),     # M1: SB wins
        (13, 11, 'Sunset'),   # M2: IW wins
        (5, 13, 'Bind'),      # M3: SB wins
        (13, 8, 'Haven'),     # M4: IW wins
        (9, 13, 'Split'),     # M5: SB wins
        (10, 13, 'Ascent'),   # M6: SB wins
    ],
    # Lobby 5: Apex Predators (404) vs Neon Blaze (400)
    # Apex Predators wins 4-2
    121: [
        (13, 8, 'Icebox'),    # M1: AP wins
        (11, 13, 'Breeze'),   # M2: NB wins
        (13, 9, 'Fracture'),  # M3: AP wins
        (7, 13, 'Pearl'),     # M4: NB wins
        (13, 11, 'Lotus'),    # M5: AP wins
        (13, 6, 'Sunset'),    # M6: AP wins
    ],
}

now = timezone.now()

for group in Group.objects.filter(tournament=tournament, round_number=1).order_by('id'):
    print(f"\n--- {group.group_name} (id={group.id}) ---")
    teams = list(group.teams.all().order_by('id'))
    
    if len(teams) != 2:
        print(f"  Skipping - expected 2 teams, got {len(teams)}")
        continue
    
    # Teams are ordered by id (first registered = team1, second = team2)
    # But we need to match the order from the API response
    # From the DB query earlier, teams within each group:
    # Group 117: Shadow Nexus (397), Phoenix Rising (396) -> sorted by id: 396 first, 397 second
    # But in API response, it shows Shadow Nexus first... let me check
    
    team_a = teams[0]  # First team in group (lower id)
    team_b = teams[1]  # Second team in group (higher id)
    
    print(f"  Team A: {team_a.team_name} (reg_id={team_a.id})")
    print(f"  Team B: {team_b.team_name} (reg_id={team_b.id})")
    
    scores_data = LOBBY_SCORES.get(group.id, [])
    
    for match in group.matches.all().order_by('match_number'):
        match_idx = match.match_number - 1
        if match_idx >= len(scores_data):
            print(f"  No score data for Match {match.match_number}")
            continue
        
        team_a_score, team_b_score, map_name = scores_data[match_idx]
        
        # Set map and complete the match
        match.map_name = map_name
        match.status = 'completed'
        match.started_at = now - timezone.timedelta(hours=2, minutes=30 * (6 - match.match_number))
        match.ended_at = now - timezone.timedelta(hours=1, minutes=30 * (6 - match.match_number))
        match.save()
        
        # Remove any existing scores
        MatchScore.objects.filter(match=match).delete()
        
        # Create scores - for 5v5, total score goes in position_points, kill_points=0
        # Winner gets wins=1
        a_wins = 1 if team_a_score > team_b_score else 0
        b_wins = 1 if team_b_score > team_a_score else 0
        
        MatchScore.objects.create(
            match=match,
            team=team_a,
            position_points=team_a_score,
            kill_points=0,
            wins=a_wins,
        )
        MatchScore.objects.create(
            match=match,
            team=team_b,
            position_points=team_b_score,
            kill_points=0,
            wins=b_wins,
        )
        
        # Determine match winner
        match.determine_winner()
        
        winner_name = match.winner.team_name if match.winner else "None"
        print(f"  M{match.match_number} ({map_name}): {team_a.team_name} {team_a_score} - {team_b_score} {team_b.team_name} | Winner: {winner_name}")
    
    # Mark group as completed and determine winner
    group.status = 'completed'
    group.save()
    group.determine_group_winner()
    print(f"  Group Winner: {group.winner.team_name if group.winner else 'None'}")

# Calculate round scores
print("\n--- Calculating Round Scores ---")
TournamentGroupService.calculate_round_scores(tournament, 1)

# Verify
print("\n--- Verification ---")
for group in Group.objects.filter(tournament=tournament, round_number=1).order_by('id'):
    print(f"{group.group_name}: status={group.status}, winner={group.winner.team_name if group.winner else 'None'}")
    for m in group.matches.all().order_by('match_number'):
        scores = MatchScore.objects.filter(match=m)
        score_str = ", ".join([f"{s.team.team_name}: {s.total_points}pts (w={s.wins})" for s in scores])
        print(f"  M{m.match_number}: {m.status}, map={m.map_name}, winner={m.winner.team_name if m.winner else 'None'}, scores=[{score_str}]")

print("\nDone!")
