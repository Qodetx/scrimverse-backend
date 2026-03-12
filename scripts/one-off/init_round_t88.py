from tournaments.models import Tournament
from tournaments.services import TournamentGroupService

TOURNAMENT_ID = 88
ROUND_NUMBER = 1
MATCHES_PER_LOBBY = 1

try:
    t = Tournament.objects.get(id=TOURNAMENT_ID)
except Tournament.DoesNotExist:
    print(f"ERROR: Tournament {TOURNAMENT_ID} not found")
else:
    res = TournamentGroupService.create_5v5_groups(t, ROUND_NUMBER, matches_per_group=MATCHES_PER_LOBBY)

    groups = []
    for g in res.get('groups', []):
        groups.append({
            'id': g.id,
            'group_name': g.group_name,
            'teams': [ {'id': reg.id, 'team_name': reg.team_name} for reg in g.teams.all() ]
        })

    print('RESULT_SUMMARY')
    print('num_lobbies:', res.get('total_lobbies'))
    bye = res.get('bye_team')
    if bye:
        print('bye_team:', {'id': bye.id, 'team_name': bye.team_name})
    else:
        print('bye_team: None')
    print('bye_message:', res.get('bye_message'))
    print('groups:', groups)

    t.refresh_from_db()
    print('tournament.round_status:', t.round_status)
    print('tournament.selected_teams:', t.selected_teams)
