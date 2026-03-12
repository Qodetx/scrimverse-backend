from accounts.models import Team, TeamStatistics

team = Team.objects.first()
if not team:
    print("No teams found in DB. Please create a team first.")
else:
    print(f"Using Team ID {team.id} - {team.name}")

    def create_if_missing(game_name, t_wins, t_pos, t_kills, s_wins=0, s_pos=0, s_kills=0):
        stat = TeamStatistics.objects.filter(team=team, game_name=game_name).first()
        if stat:
            print(f"{game_name} stats already exist: {stat}")
            return stat
        stat = TeamStatistics.objects.create(
            team=team,
            game_name=game_name,
            tournament_wins=t_wins,
            tournament_position_points=t_pos,
            tournament_kill_points=t_kills,
            scrim_wins=s_wins,
            scrim_position_points=s_pos,
            scrim_kill_points=s_kills,
        )
        stat.update_total_points()
        print(f"Created {game_name} stats: {stat} (total_points={stat.total_points})")
        return stat

    create_if_missing('Valorant', 5, 800, 400, s_wins=2, s_pos=200, s_kills=100)
    create_if_missing('COD', 3, 600, 300, s_wins=1, s_pos=150, s_kills=75)
    create_if_missing('BGMI', 10, 1500, 800, s_wins=5, s_pos=400, s_kills=200)

    # Create/ensure ALL aggregate exists
    all_stat = TeamStatistics.objects.filter(team=team, game_name='ALL').first()
    if not all_stat:
        total_t_pos = sum([s.tournament_position_points for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')])
        total_t_kills = sum([s.tournament_kill_points for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')])
        total_scrim_pos = sum([s.scrim_position_points for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')])
        total_scrim_kills = sum([s.scrim_kill_points for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')])
        all_stat = TeamStatistics.objects.create(
            team=team,
            game_name='ALL',
            tournament_wins=sum([s.tournament_wins for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')]),
            tournament_position_points=total_t_pos,
            tournament_kill_points=total_t_kills,
            scrim_wins=sum([s.scrim_wins for s in TeamStatistics.objects.filter(team=team).exclude(game_name='ALL')]),
            scrim_position_points=total_scrim_pos,
            scrim_kill_points=total_scrim_kills,
        )
        all_stat.update_total_points()
        print(f"Created ALL stats: {all_stat} (total_points={all_stat.total_points})")
    else:
        print(f"ALL stats already exist: {all_stat}")

    print('\nCurrent stats for team:')
    for s in TeamStatistics.objects.filter(team=team):
        print(f"- {s.game_name}: total_points={s.total_points}, tournament_wins={s.tournament_wins}")
