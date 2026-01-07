"""
Comprehensive Tournament and Scrim Data Generation Script
Creates 60 teams (240 players), 3 completed tournaments, 2 completed scrims,
1 upcoming tournament, and 1 upcoming scrim with realistic data
"""

import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from accounts.models import HostProfile, PlayerProfile, Team, TeamMember, TeamStatistics
from tournaments.models import Group, Match, MatchScore, RoundScore, Tournament, TournamentRegistration

User = get_user_model()

# Game configurations
GAMES = ["BGMI", "Free Fire", "Valorant"]
GAME_MODES = {"BGMI": ["Squad", "Duo"], "Free Fire": ["Squad", "Duo"], "Valorant": ["5v5"]}

# Team name prefixes and suffixes for variety
TEAM_PREFIXES = [
    "Alpha",
    "Beta",
    "Gamma",
    "Delta",
    "Omega",
    "Phoenix",
    "Dragon",
    "Tiger",
    "Wolf",
    "Eagle",
    "Viper",
    "Cobra",
    "Falcon",
    "Hawk",
    "Raven",
    "Storm",
    "Thunder",
    "Lightning",
    "Blaze",
    "Inferno",
]
TEAM_SUFFIXES = ["Esports", "Gaming", "Squad", "Clan", "Team", "Warriors", "Legends", "Champions", "Elite", "Pro"]

# Player name components
FIRST_NAMES = [
    "Aditya",
    "Rahul",
    "Arjun",
    "Rohan",
    "Karan",
    "Vikram",
    "Amit",
    "Raj",
    "Sanjay",
    "Priya",
    "Sneha",
    "Anjali",
    "Pooja",
    "Riya",
    "Neha",
    "Sakshi",
    "Divya",
    "Shreya",
    "Kavya",
    "Isha",
]
LAST_NAMES = ["Kumar", "Sharma", "Patel", "Singh", "Gupta", "Reddy", "Verma", "Joshi", "Mehta", "Nair"]

# Scoring configurations
POSITION_POINTS = {1: 10, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2, 7: 1, 8: 1}


def clear_existing_data():
    """Clear existing tournament and team data"""
    print("🗑️  Clearing existing data...")

    # Delete in correct order to avoid foreign key constraints
    MatchScore.objects.all().delete()
    RoundScore.objects.all().delete()
    Match.objects.all().delete()
    Group.objects.all().delete()
    TournamentRegistration.objects.all().delete()
    Tournament.objects.all().delete()

    TeamMember.objects.all().delete()
    TeamStatistics.objects.all().delete()
    Team.objects.all().delete()

    PlayerProfile.objects.all().delete()
    HostProfile.objects.all().delete()
    User.objects.filter(user_type__in=["player", "host"]).delete()

    print("✅ Data cleared successfully")


def create_host():
    """Create a host user"""
    print("👤 Creating host...")

    host_user = User.objects.create_user(
        username="tournament_host",
        email="host@scrimverse.com",
        password="password123",
        user_type="host",
        phone_number="9876543210",
    )

    HostProfile.objects.create(
        user=host_user,
        bio="Professional tournament organizer",
        verified=True,
        total_tournaments_hosted=10,
        rating=Decimal("4.8"),
    )

    print(f"✅ Created host: {host_user.username}")
    return host_user


def create_teams_and_players(num_teams=60):
    """Create teams with 4 players each"""
    print(f"\n👥 Creating {num_teams} teams with 240 players...")

    teams = []
    all_players = []

    for i in range(num_teams):
        # Create team name
        prefix = random.choice(TEAM_PREFIXES)
        suffix = random.choice(TEAM_SUFFIXES)
        team_name = f"{prefix} {suffix}"

        # Ensure unique team name
        counter = 1
        original_name = team_name
        while Team.objects.filter(name=team_name).exists():
            team_name = f"{original_name} {counter}"
            counter += 1

        # Create captain (player 1)
        captain_username = f"player_{i*4 + 1}"
        captain_email = f"player{i*4 + 1}@scrimverse.com"

        captain = User.objects.create_user(
            username=captain_username,
            email=captain_email,
            password="password123",
            user_type="player",
            phone_number=f"98765{str(i*4 + 1).zfill(5)}",
        )

        PlayerProfile.objects.create(
            user=captain,
            preferred_games=[random.choice(GAMES)],
            skill_level=random.choice(["Beginner", "Intermediate", "Advanced", "Pro"]),
            bio=f"Captain of {team_name}",
        )

        all_players.append(captain)

        # Create team
        team = Team.objects.create(name=team_name, captain=captain, is_temporary=False)

        # Create team statistics
        TeamStatistics.objects.create(team=team)

        # Add captain as team member
        TeamMember.objects.create(team=team, user=captain, username=captain_username, is_captain=True)

        # Create 3 more team members
        for j in range(1, 4):
            player_num = i * 4 + j + 1
            player_username = f"player_{player_num}"
            player_email = f"player{player_num}@scrimverse.com"

            player = User.objects.create_user(
                username=player_username,
                email=player_email,
                password="password123",
                user_type="player",
                phone_number=f"98765{str(player_num).zfill(5)}",
            )

            PlayerProfile.objects.create(
                user=player,
                preferred_games=[random.choice(GAMES)],
                skill_level=random.choice(["Beginner", "Intermediate", "Advanced", "Pro"]),
            )

            all_players.append(player)

            TeamMember.objects.create(team=team, user=player, username=player_username, is_captain=False)

        teams.append(team)

        if (i + 1) % 10 == 0:
            print(f"  Created {i + 1}/{num_teams} teams...")

    print(f"✅ Created {len(teams)} teams with {len(all_players)} players")
    return teams, all_players


def create_completed_tournament(host, teams, tournament_num):
    """Create a completed tournament with full results"""
    print(f"\n🏆 Creating completed tournament #{tournament_num}...")

    game = random.choice(GAMES)
    game_mode = random.choice(GAME_MODES[game])

    # Create tournament 30 days ago
    start_date = timezone.now() - timedelta(days=30 - tournament_num * 10)
    end_date = start_date + timedelta(days=2)

    tournament = Tournament.objects.create(
        title=f"Championship Series {tournament_num}",
        description=f"Professional {game} tournament with top teams",
        game_name=game,
        game_mode=game_mode,
        host=host.host_profile,
        event_mode="TOURNAMENT",
        entry_fee=Decimal("500.00"),
        prize_pool=Decimal("50000.00"),
        max_participants=60,
        current_participants=60,
        tournament_start=start_date,
        tournament_end=end_date,
        registration_start=start_date - timedelta(days=7),
        registration_end=start_date - timedelta(days=1),
        status="completed",
        rounds=[
            {"round": 1, "qualifying_teams": 24},
            {"round": 2, "qualifying_teams": 12},
            {"round": 3, "qualifying_teams": 0},  # Finals
        ],
        current_round=0,  # Completed
        rules="Standard tournament rules apply",
    )

    # Register all teams
    registrations = []
    for team in teams:
        reg = TournamentRegistration.objects.create(
            tournament=tournament,
            player=team.captain.player_profile,
            team=team,
            team_name=team.name,
            team_members=[
                {"username": member.username, "in_game_name": member.username} for member in team.members.all()
            ],
            status="confirmed",
            payment_status=True,
        )
        registrations.append(reg)

    # Simulate 3 rounds
    winners = {}
    for round_num in range(1, 4):
        print(f"  Simulating Round {round_num}...")

        if round_num == 1:
            round_teams = registrations
            num_groups = 4
            matches_per_group = 4
            qualifying = 24
        elif round_num == 2:
            # Get top 24 from round 1
            round_teams = sorted(registrations, key=lambda x: random.random())[:24]
            num_groups = 4
            matches_per_group = 3
            qualifying = 12
        else:  # Round 3 (Finals)
            round_teams = sorted(registrations, key=lambda x: random.random())[:12]
            num_groups = 2
            matches_per_group = 3
            qualifying = 0

        # Create groups
        teams_per_group = len(round_teams) // num_groups
        for group_num in range(num_groups):
            group_letter = chr(65 + group_num)  # A, B, C, D

            group = Group.objects.create(
                tournament=tournament,
                round_number=round_num,
                group_name=f"Group {group_letter}",
                qualifying_teams=qualifying // num_groups if qualifying > 0 else 0,
                status="completed",
            )

            # Assign teams to group
            start_idx = group_num * teams_per_group
            end_idx = start_idx + teams_per_group
            group_teams = round_teams[start_idx:end_idx]

            for reg in group_teams:
                group.teams.add(reg)

            # Create matches
            for match_num in range(1, matches_per_group + 1):
                match = Match.objects.create(
                    group=group,
                    match_number=match_num,
                    match_id=f"ROOM{round_num}{group_num}{match_num}",
                    match_password=f"PASS{random.randint(1000, 9999)}",
                    status="completed",
                    started_at=start_date + timedelta(hours=round_num * 8 + match_num),
                    ended_at=start_date + timedelta(hours=round_num * 8 + match_num + 1),
                )

                # Create scores for each team
                positions = list(range(1, len(group_teams) + 1))
                random.shuffle(positions)

                for idx, reg in enumerate(group_teams):
                    position = positions[idx]
                    kills = random.randint(0, 15)
                    position_pts = POSITION_POINTS.get(position, 0)
                    kill_pts = kills

                    MatchScore.objects.create(
                        match=match,
                        team=reg,
                        wins=1 if position == 1 else 0,
                        position_points=position_pts,
                        kill_points=kill_pts,
                        total_points=position_pts + kill_pts,
                    )

        # Calculate round results and determine winners
        round_scores = {}
        for reg in round_teams:
            scores = MatchScore.objects.filter(
                match__group__tournament=tournament, match__group__round_number=round_num, team=reg
            ).aggregate(total_pos=models.Sum("position_points"), total_kills=models.Sum("kill_points"))

            total = (scores["total_pos"] or 0) + (scores["total_kills"] or 0)
            round_scores[reg.id] = total

            # Create RoundScore
            RoundScore.objects.create(
                tournament=tournament,
                round_number=round_num,
                team=reg,
                position_points=scores["total_pos"] or 0,
                kill_points=scores["total_kills"] or 0,
                total_points=total,
            )

        # Determine round winner
        if round_scores:
            winner_reg_id = max(round_scores, key=round_scores.get)
            winners[str(round_num)] = winner_reg_id

    # Set tournament winners
    tournament.winners = winners
    tournament.save()

    # Update team statistics
    update_tournament_statistics(tournament, registrations)

    print(f"✅ Completed tournament #{tournament_num} created")
    return tournament


def create_completed_scrim(host, teams, scrim_num):
    """Create a completed scrim with results"""
    print(f"\n⚔️  Creating completed scrim #{scrim_num}...")

    # Select 25 random teams
    selected_teams = random.sample(teams, 25)

    game = random.choice(GAMES)
    game_mode = random.choice(GAME_MODES[game])

    # Create scrim 20 days ago
    start_date = timezone.now() - timedelta(days=20 - scrim_num * 5)
    end_date = start_date + timedelta(hours=3)

    scrim = Tournament.objects.create(
        title=f"Practice Scrim {scrim_num}",
        description=f"Casual {game} scrim session",
        game_name=game,
        game_mode=game_mode,
        host=host.host_profile,
        event_mode="SCRIM",
        entry_fee=Decimal("100.00"),
        prize_pool=Decimal("5000.00"),
        max_participants=25,
        current_participants=25,
        tournament_start=start_date,
        tournament_end=end_date,
        registration_start=start_date - timedelta(days=3),
        registration_end=start_date - timedelta(hours=2),
        status="completed",
        rounds=[{"round": 1, "qualifying_teams": 0}],  # Scrims have 1 round
        current_round=0,
        rules="Casual scrim rules",
    )

    # Register teams
    registrations = []
    for team in selected_teams:
        reg = TournamentRegistration.objects.create(
            tournament=scrim,
            player=team.captain.player_profile,
            team=team,
            team_name=team.name,
            team_members=[
                {"username": member.username, "in_game_name": member.username} for member in team.members.all()
            ],
            status="confirmed",
            payment_status=True,
        )
        registrations.append(reg)

    # Create single group with 6 matches
    group = Group.objects.create(
        tournament=scrim, round_number=1, group_name="Group A", qualifying_teams=0, status="completed"
    )

    for reg in registrations:
        group.teams.add(reg)

    # Create 6 matches
    for match_num in range(1, 7):
        match = Match.objects.create(
            group=group,
            match_number=match_num,
            match_id=f"SCRIM{scrim_num}M{match_num}",
            match_password=f"PASS{random.randint(1000, 9999)}",
            status="completed",
            started_at=start_date + timedelta(minutes=match_num * 30),
            ended_at=start_date + timedelta(minutes=match_num * 30 + 25),
        )

        # Create scores
        positions = list(range(1, 26))
        random.shuffle(positions)

        for idx, reg in enumerate(registrations):
            position = positions[idx]
            kills = random.randint(0, 12)
            position_pts = POSITION_POINTS.get(position, 0)
            kill_pts = kills

            MatchScore.objects.create(
                match=match,
                team=reg,
                wins=1 if position == 1 else 0,
                position_points=position_pts,
                kill_points=kill_pts,
                total_points=position_pts + kill_pts,
            )

    # Calculate final scores and winner
    round_scores = {}
    for reg in registrations:
        scores = MatchScore.objects.filter(match__group__tournament=scrim, team=reg).aggregate(
            total_pos=models.Sum("position_points"), total_kills=models.Sum("kill_points")
        )

        total = (scores["total_pos"] or 0) + (scores["total_kills"] or 0)
        round_scores[reg.id] = total

        RoundScore.objects.create(
            tournament=scrim,
            round_number=1,
            team=reg,
            position_points=scores["total_pos"] or 0,
            kill_points=scores["total_kills"] or 0,
            total_points=total,
        )

    # Set winner
    if round_scores:
        winner_reg_id = max(round_scores, key=round_scores.get)
        scrim.winners = {"1": winner_reg_id}
        scrim.save()

    # Update scrim statistics
    update_scrim_statistics(scrim, registrations)

    print(f"✅ Completed scrim #{scrim_num} created")
    return scrim


def create_upcoming_tournament(host, teams):
    """Create an upcoming tournament with all teams registered"""
    print(f"\n📅 Creating upcoming tournament...")

    game = random.choice(GAMES)
    game_mode = random.choice(GAME_MODES[game])

    start_date = timezone.now() + timedelta(days=3)
    end_date = start_date + timedelta(days=2)

    tournament = Tournament.objects.create(
        title="Upcoming Championship",
        description=f"Next big {game} tournament",
        game_name=game,
        game_mode=game_mode,
        host=host.host_profile,
        event_mode="TOURNAMENT",
        entry_fee=Decimal("500.00"),
        prize_pool=Decimal("75000.00"),
        max_participants=60,
        current_participants=60,
        tournament_start=start_date,
        tournament_end=end_date,
        registration_start=timezone.now() - timedelta(days=5),
        registration_end=timezone.now() + timedelta(days=2),
        status="upcoming",
        rounds=[
            {"round": 1, "qualifying_teams": 24},
            {"round": 2, "qualifying_teams": 12},
            {"round": 3, "qualifying_teams": 0},
        ],
        current_round=1,
        rules="Standard tournament rules apply",
    )

    # Register all teams
    for team in teams:
        TournamentRegistration.objects.create(
            tournament=tournament,
            player=team.captain.player_profile,
            team=team,
            team_name=team.name,
            team_members=[
                {"username": member.username, "in_game_name": member.username} for member in team.members.all()
            ],
            status="confirmed",
            payment_status=True,
        )

    print(f"✅ Upcoming tournament created with {len(teams)} teams registered")
    return tournament


def create_upcoming_scrim(host, teams):
    """Create an upcoming scrim with 25 teams registered"""
    print(f"\n📅 Creating upcoming scrim...")

    selected_teams = random.sample(list(teams), 25)

    game = random.choice(GAMES)
    game_mode = random.choice(GAME_MODES[game])

    start_date = timezone.now() + timedelta(days=1)
    end_date = start_date + timedelta(hours=3)

    scrim = Tournament.objects.create(
        title="Upcoming Practice Scrim",
        description=f"Practice session for {game}",
        game_name=game,
        game_mode=game_mode,
        host=host.host_profile,
        event_mode="SCRIM",
        entry_fee=Decimal("100.00"),
        prize_pool=Decimal("5000.00"),
        max_participants=25,
        current_participants=25,
        tournament_start=start_date,
        tournament_end=end_date,
        registration_start=timezone.now() - timedelta(days=2),
        registration_end=timezone.now() + timedelta(hours=12),
        status="upcoming",
        rounds=[{"round": 1, "qualifying_teams": 0}],
        current_round=1,
        rules="Casual scrim rules",
    )

    # Register teams
    for team in selected_teams:
        TournamentRegistration.objects.create(
            tournament=scrim,
            player=team.captain.player_profile,
            team=team,
            team_name=team.name,
            team_members=[
                {"username": member.username, "in_game_name": member.username} for member in team.members.all()
            ],
            status="confirmed",
            payment_status=True,
        )

    print(f"✅ Upcoming scrim created with {len(selected_teams)} teams registered")
    return scrim


def update_tournament_statistics(tournament, registrations):
    """Update team statistics for tournament"""

    for reg in registrations:
        if not reg.team:
            continue

        stats, _ = TeamStatistics.objects.get_or_create(team=reg.team)

        # Get tournament scores
        scores = MatchScore.objects.filter(match__group__tournament=tournament, team=reg).aggregate(
            total_pos=models.Sum("position_points"), total_kills=models.Sum("kill_points")
        )

        # Update tournament-specific stats
        stats.tournament_position_points += scores["total_pos"] or 0
        stats.tournament_kill_points += scores["total_kills"] or 0

        # Check if winner
        if tournament.winners:
            for round_num, winner_id in tournament.winners.items():
                if winner_id == reg.id and round_num == str(len(tournament.rounds)):
                    stats.tournament_wins += 1

        # Update combined stats
        stats.total_position_points = stats.tournament_position_points + stats.scrim_position_points
        stats.total_kill_points = stats.tournament_kill_points + stats.scrim_kill_points
        stats.update_total_points()


def update_scrim_statistics(scrim, registrations):
    """Update team statistics for scrim"""

    for reg in registrations:
        if not reg.team:
            continue

        stats, _ = TeamStatistics.objects.get_or_create(team=reg.team)

        # Get scrim scores
        scores = MatchScore.objects.filter(match__group__tournament=scrim, team=reg).aggregate(
            total_pos=models.Sum("position_points"), total_kills=models.Sum("kill_points")
        )

        # Update scrim-specific stats
        stats.scrim_position_points += scores["total_pos"] or 0
        stats.scrim_kill_points += scores["total_kills"] or 0

        # Check if winner
        if scrim.winners and scrim.winners.get("1") == reg.id:
            stats.scrim_wins += 1

        # Update combined stats
        stats.total_position_points = stats.tournament_position_points + stats.scrim_position_points
        stats.total_kill_points = stats.tournament_kill_points + stats.scrim_kill_points
        stats.update_total_points()


def main():
    """Main execution function"""
    print("\n" + "=" * 60)
    print("🎮 SCRIMVERSE DATA GENERATION SCRIPT")
    print("=" * 60)

    # Clear existing data
    clear_existing_data()

    # Create host
    host = create_host()

    # Create teams and players
    teams, players = create_teams_and_players(60)

    # Create 3 completed tournaments
    for i in range(1, 4):
        create_completed_tournament(host, teams, i)

    # Create 2 completed scrims
    for i in range(1, 3):
        create_completed_scrim(host, teams, i)

    # Create 1 upcoming tournament
    create_upcoming_tournament(host, teams)

    # Create 1 upcoming scrim
    create_upcoming_scrim(host, teams)

    print("\n" + "=" * 60)
    print("✅ DATA GENERATION COMPLETE!")
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"  - Teams created: {Team.objects.count()}")
    print(f"  - Players created: {User.objects.filter(user_type='player').count()}")
    print(
        f"  - Completed Tournaments: {Tournament.objects.filter(event_mode='TOURNAMENT', status='completed').count()}"
    )
    print(f"  - Completed Scrims: {Tournament.objects.filter(event_mode='SCRIM', status='completed').count()}")
    print(f"  - Upcoming Tournaments: {Tournament.objects.filter(event_mode='TOURNAMENT', status='upcoming').count()}")
    print(f"  - Upcoming Scrims: {Tournament.objects.filter(event_mode='SCRIM', status='upcoming').count()}")
    print(f"\n🔑 Login Credentials:")
    print(f"  Host: host@scrimverse.com / password123")
    print(f"  Players: player1@scrimverse.com to player240@scrimverse.com / password123")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
