import random
from tournaments.services import TournamentGroupService
from tournaments.models import Tournament, Group, Match, MatchScore

TOURNAMENT_ID = 26

try:
    tournament = Tournament.objects.get(id=TOURNAMENT_ID)
except Exception as e:
    print(f"Tournament not found: {e}")
    raise SystemExit(1)

final_round = max(r['round'] for r in tournament.rounds)
start_round = tournament.current_round + 1

print(f"Simulating rounds {start_round} to {final_round} for Tournament {tournament.id}")

for round_number in range(start_round, final_round + 1):
    print(f"\n--- Round {round_number} ---")
    res = TournamentGroupService.create_5v5_groups(tournament, round_number, matches_per_group=3)
    if res.get('error'):
        print('Error creating groups:', res['error'])
        break

    groups = res['groups']
    print(f"  Created {len(groups)} lobbies")

    qualified = []

    for group in groups:
        print(f"  Simulating {group.group_name}: {[t.team_name for t in group.teams.all()]}")
        matches = list(group.matches.order_by('match_number'))
        teams = list(group.teams.all())
        if len(teams) != 2:
            print('   Skipping non-2-team group')
            continue
        team_a = teams[0]
        team_b = teams[1]

        for match in matches:
            a_pos = random.randint(10,25)
            b_pos = random.randint(5,20)
            a_kills = random.randint(5,15)
            b_kills = random.randint(0,10)
            if b_pos + b_kills > a_pos + a_kills:
                a_pos, b_pos = b_pos, a_pos
                a_kills, b_kills = b_kills, a_kills

            ms_a = MatchScore.objects.create(match=match, team=team_a, wins=1, position_points=a_pos, kill_points=a_kills)
            ms_b = MatchScore.objects.create(match=match, team=team_b, wins=0, position_points=b_pos, kill_points=b_kills)

            match.determine_winner()
            match.status = 'completed'
            match.save(update_fields=['status','winner'])

            print(f"    Match {match.match_number}: {team_a.team_name} {ms_a.total_points} - {team_b.team_name} {ms_b.total_points} | Winner: {match.winner.team_name if match.winner else 'None'}")

        group.determine_group_winner()
        group.status = 'completed'
        group.save(update_fields=['status','winner'])
        print(f"    Group winner: {group.winner.team_name if group.winner else 'None'}")
        if group.winner:
            qualified.append(group.winner.id)

    # Update tournament selections and status
    if not tournament.selected_teams:
        tournament.selected_teams = {}
    tournament.selected_teams[str(round_number)] = qualified

    if not tournament.round_status:
        tournament.round_status = {}
    tournament.round_status[str(round_number)] = 'completed'
    tournament.current_round = round_number

    # If final round, set tournament winner & mark completed
    if round_number == final_round:
        winner_id = qualified[0] if qualified else None
        if winner_id:
            if not tournament.winners:
                tournament.winners = {}
            tournament.winners[str(round_number)] = winner_id
            tournament.status = 'completed'

            tournament.save(update_fields=['selected_teams','round_status','current_round','winners','status'])
            print(f"Tournament completed. Winner registration ID: {winner_id}")
        else:
            tournament.save(update_fields=['selected_teams','round_status','current_round'])
            print('No winner determined')
    else:
        tournament.save(update_fields=['selected_teams','round_status','current_round'])
        print(f"Qualified for next round: {qualified}")

print('\nSimulation finished.')
