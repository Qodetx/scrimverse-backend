import random
from tournaments.services import TournamentGroupService
from tournaments.models import Tournament, Group, Match, MatchScore

# Use the COD tournament created earlier - update ID if different
TOURNAMENT_ID = 26

try:
    tournament = Tournament.objects.get(id=TOURNAMENT_ID)
except Exception as e:
    print(f"Tournament not found: {e}")
    raise SystemExit(1)

print(f"Creating 5v5 lobbies for Tournament: {tournament.id} - {tournament.title}")
res = TournamentGroupService.create_5v5_groups(tournament, round_number=1, matches_per_group=3)

if res.get('error'):
    print('Error creating groups:', res['error'])
    raise SystemExit(1)

groups = res['groups']
print(f"Created {len(groups)} lobbies. Bye team: {res.get('bye_team')}")

# Simulate matches: give team A wins in most matches to deterministically produce winners
for group in groups:
    print(f"Simulating group: {group.group_name} | Teams: {[t.team_name for t in group.teams.all()]}")
    matches = list(group.matches.order_by('match_number'))
    teams = list(group.teams.all())
    if len(teams) != 2:
        print('Skipping non-2-team group')
        continue
    team_a = teams[0]
    team_b = teams[1]

    for match in matches:
        # Randomized but biased to team_a to ensure a winner
        a_pos = random.randint(10, 25)
        b_pos = random.randint(5, 20)
        a_kills = random.randint(5, 15)
        b_kills = random.randint(0, 10)

        if b_pos + b_kills > a_pos + a_kills:
            # swap to keep team_a winning mostly
            a_pos, b_pos = b_pos, a_pos
            a_kills, b_kills = b_kills, a_kills

        # Create scores
        ms_a = MatchScore.objects.create(match=match, team=team_a, wins=1, position_points=a_pos, kill_points=a_kills)
        ms_b = MatchScore.objects.create(match=match, team=team_b, wins=0, position_points=b_pos, kill_points=b_kills)

        # Determine winner and mark completed
        match.determine_winner()
        match.status = 'completed'
        match.save(update_fields=['status','winner'])

        print(f"  Match {match.match_number}: {team_a.team_name} {ms_a.total_points} - {team_b.team_name} {ms_b.total_points} | Winner: {match.winner.team_name if match.winner else 'None'}")

    # After all matches, determine group winner and mark completed
    group.determine_group_winner()
    group.status = 'completed'
    group.save(update_fields=['status','winner'])
    print(f"  Group winner: {group.winner.team_name if group.winner else 'None'}")

# Calculate round scores
TournamentGroupService.calculate_round_scores(tournament, 1)

# Collect qualified (winners) for next round
qualified = []
for group in groups:
    if group.winner:
        qualified.append(group.winner.id)

if not tournament.selected_teams:
    tournament.selected_teams = {}

tournament.selected_teams['1'] = qualified
# mark current round as completed and set current_round
if not tournament.round_status:
    tournament.round_status = {}

tournament.round_status['1'] = 'completed'

tournament.current_round = 1

tournament.save(update_fields=['selected_teams','round_status','current_round'])

print('Simulation complete.')
print('Qualified teams for next round:', qualified)
