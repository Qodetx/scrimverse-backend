import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import Team, TeamStatistics

def inspect_all_teams():
    teams = Team.objects.all()
    for team in teams:
        stats = TeamStatistics.objects.filter(team=team)
        if not stats.exists():
            continue
            
        print(f"Team: {team.name} (ID: {team.id}, Game: {team.game})")
        print("-" * 50)
        
        for s in stats:
            print(f"Game: {s.game_name}")
            print(f"  Matches Played: {s.matches_played}")
            print(f"  Tournament Matches Played: {s.tournament_matches_played}")
            print(f"  Scrim Matches Played: {s.scrim_matches_played}")
            print(f"  Tournament Wins: {s.tournament_wins}")
            print(f"  Scrim Wins: {s.scrim_wins}")
            print(f"  Rank: {s.rank}")
            print(f"  Tournament Rank: {s.tournament_rank}")
            print(f"  Scrim Rank: {s.scrim_rank}")
            print("-" * 30)
        print("\n")

if __name__ == "__main__":
    inspect_all_teams()
