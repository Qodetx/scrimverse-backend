"""
Comprehensive test cases for tournaments Celery tasks
"""
from unittest.mock import MagicMock, patch

from django.core.cache import cache

import pytest

from accounts.models import TeamStatistics
from tests.factories import (
    HostProfileFactory,
    PlayerProfileFactory,
    TeamFactory,
    TournamentFactory,
    TournamentRegistrationFactory,
)
from tournaments.models import Group, Match, MatchScore, RoundScore
from tournaments.tasks import (
    create_tournament_groups,
    process_match_scores,
    process_round_scores,
    process_tournament_banner,
    process_tournament_registration,
    refresh_all_host_dashboards,
    update_host_dashboard_stats,
    update_leaderboard,
    update_platform_statistics,
)


@pytest.mark.django_db
def test_update_leaderboard():
    """Test the update_leaderboard task recalculates stats and ranks correctly"""
    # 1. Setup teams
    team1 = TeamFactory(name="Team Alpha", is_temporary=False)
    team2 = TeamFactory(name="Team Beta", is_temporary=False)

    # 2. Setup completed tournament
    host = HostProfileFactory()
    tournament = TournamentFactory(
        host=host,
        status="completed",
        event_mode="TOURNAMENT",
        rounds=[{"round": 1, "max_teams": 2, "qualifying_teams": 1}],
    )

    # 3. Setup registrations
    reg1 = TournamentRegistrationFactory(tournament=tournament, team=team1, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, team=team2, status="confirmed")

    # 4. Setup scores and winner
    # We need a Group and Match to have MatchScores
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="Finals")
    match = Match.objects.create(group=group, match_number=1, status="completed")

    # reg1 wins
    MatchScore.objects.create(match=match, team=reg1, position_points=10, kill_points=5)
    MatchScore.objects.create(match=match, team=reg2, position_points=5, kill_points=2)

    tournament.winners = {"1": reg1.id}
    tournament.save()

    # 5. Run task
    result = update_leaderboard()

    # 6. Verify stats
    assert result["teams_updated"] >= 2

    stats1 = TeamStatistics.objects.get(team=team1)
    stats2 = TeamStatistics.objects.get(team=team2)

    assert stats1.tournament_wins == 1
    assert stats1.total_points == 15
    assert stats2.tournament_wins == 0
    assert stats2.total_points == 7

    assert stats1.rank == 1
    assert stats2.rank == 2

    # Verify Team model fields
    team1.refresh_from_db()
    assert team1.wins == 1
    assert team1.total_matches == 1


@pytest.mark.django_db
def test_update_leaderboard_with_scrim():
    """Test Scrim wins are counted separately in leaderboard"""
    team = TeamFactory(is_temporary=False)
    host = HostProfileFactory()
    scrim = TournamentFactory(host=host, status="completed", event_mode="SCRIM", rounds=[{"round": 1}])
    reg = TournamentRegistrationFactory(tournament=scrim, team=team, status="confirmed")

    # reg wins
    scrim.winners = {"1": reg.id}
    scrim.save()

    update_leaderboard()

    stats = TeamStatistics.objects.get(team=team)
    assert stats.scrim_wins == 1
    assert stats.tournament_wins == 0

    team.refresh_from_db()
    assert team.wins == 1


@pytest.mark.django_db
def test_process_tournament_registration_nonexistent():
    """Test handling of nonexistent registration ID"""
    result = process_tournament_registration(99999)
    assert "error" in result
    assert result["error"] == "Registration not found"


@pytest.mark.django_db
def test_update_platform_statistics():
    """Test update_platform_statistics caches correct values"""
    cache.clear()
    # Setup data
    host = HostProfileFactory()
    TournamentFactory(host=host, status="ongoing", prize_pool=1000)
    TournamentFactory(host=host, status="completed", prize_pool=500)
    PlayerProfileFactory()
    PlayerProfileFactory()

    result = update_platform_statistics()

    assert result["total_tournaments"] == 2
    assert result["total_players"] == 2
    assert result["active_tournaments"] == 1
    assert result["completed_tournaments"] == 1
    assert result["total_prize_money"] == "500.00"

    cached_stats = cache.get("platform:statistics")
    assert cached_stats is not None
    assert cached_stats["total_tournaments"] == 2


@pytest.mark.django_db
def test_update_host_dashboard_stats():
    """Test update_host_dashboard_stats for a specific host"""
    cache.clear()
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host, status="ongoing", entry_fee=100)
    # Add confirmed registration for revenue
    TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    result = update_host_dashboard_stats(host.id)

    assert result["matches_hosted"] == 1
    assert result["total_participants"] == 1
    assert "total_prize_pool" in result

    cached_stats = cache.get(f"host:dashboard:{host.id}")
    assert cached_stats is not None
    assert cached_stats["matches_hosted"] == 1


@pytest.mark.django_db
def test_refresh_all_host_dashboards():
    """Test refresh_all_host_dashboards triggers tasks for active hosts"""
    host1 = HostProfileFactory()
    host2 = HostProfileFactory()

    # Active host
    TournamentFactory(host=host1, status="ongoing")
    # Inactive host (completed tournament)
    TournamentFactory(host=host2, status="completed")

    with patch("tournaments.tasks.update_host_dashboard_stats.delay") as mock_delay:
        result = refresh_all_host_dashboards()
        assert result["hosts_refreshed"] == 1
        mock_delay.assert_called_once_with(host1.id)


@pytest.mark.django_db
def test_process_tournament_registration_success():
    """Test successful tournament registration processing"""
    tournament = TournamentFactory()
    # Provide dicts with 'id' to match task expectation
    registration = TournamentRegistrationFactory(
        tournament=tournament,
        status="pending",
        team_members=[{"id": 10, "name": "Player 1"}, {"id": 11, "name": "Player 2"}],
    )

    result = process_tournament_registration(registration.id)
    assert "error" not in result, f"Task returned error: {result.get('error')}"
    assert result["status"] == "confirmed"
    registration.refresh_from_db()
    assert registration.status == "confirmed"


@pytest.mark.django_db
def test_process_tournament_registration_duplicate():
    """Test registration rejection due to duplicate team members"""
    tournament = TournamentFactory()
    # Initial confirmed registration with some players
    TournamentRegistrationFactory(tournament=tournament, status="confirmed", team_members=[{"id": 1, "name": "P1"}])
    # New pending registration with same players
    reg2 = TournamentRegistrationFactory(
        tournament=tournament, status="pending", team_members=[{"id": 1, "name": "P1"}, {"id": 2, "name": "P2"}]
    )

    result = process_tournament_registration(reg2.id)

    assert result["status"] == "rejected"
    assert result["reason"] == "duplicate_players"
    reg2.refresh_from_db()
    assert reg2.status == "rejected"


@pytest.mark.django_db
def test_process_round_scores():
    """Test processing round scores and auto-qualifying teams"""
    tournament = TournamentFactory(rounds=[{"round": 1, "max_teams": 4, "qualifying_teams": 2}])
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg3 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    scores_data = [
        {"team_id": reg1.id, "position_points": 10, "kill_points": 5},
        {"team_id": reg2.id, "position_points": 8, "kill_points": 2},
        {"team_id": reg3.id, "position_points": 5, "kill_points": 1},
    ]

    result = process_round_scores(tournament.id, 1, scores_data)

    assert result["scores_saved"] == 3
    tournament.refresh_from_db()
    # Top 2 teams should be in selected_teams for round 1
    assert str(reg1.id) in [str(tid) for tid in tournament.selected_teams["1"]]
    assert str(reg2.id) in [str(tid) for tid in tournament.selected_teams["1"]]
    assert len(tournament.selected_teams["1"]) == 2


@pytest.mark.django_db
def test_process_match_scores():
    """Test processing match scores updates aggregates and group status"""
    host = HostProfileFactory()
    tournament = TournamentFactory(host=host)
    group = Group.objects.create(tournament=tournament, round_number=1, group_name="G1")
    # Match with 2 teams
    reg1 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    reg2 = TournamentRegistrationFactory(tournament=tournament, status="confirmed")
    group.teams.add(reg1, reg2)

    match = Match.objects.create(group=group, match_number=1, status="completed")

    scores_data = [
        {"team_id": reg1.id, "position_points": 10, "kill_points": 5},
        {"team_id": reg2.id, "position_points": 5, "kill_points": 2},
    ]

    result = process_match_scores(match.id, scores_data)

    assert result["scores_saved"] == 2
    assert result["group_completed"] is True
    group.refresh_from_db()
    assert group.status == "completed"

    # Verify RoundScore aggregation
    round_score1 = RoundScore.objects.get(tournament=tournament, team=reg1, round_number=1)
    assert round_score1.total_points == 15


@pytest.mark.django_db
def test_create_tournament_groups():
    """Test asynchronous group and match creation"""
    tournament = TournamentFactory(status="ongoing", rounds=[{"round": 1}])
    # Setup 4 confirmed teams
    for _ in range(4):
        TournamentRegistrationFactory(tournament=tournament, status="confirmed")

    config = {"teams_per_group": 2, "qualifying_per_group": 1, "matches_per_group": 1}

    result = create_tournament_groups(tournament.id, 1, config)

    assert result["groups_created"] == 2
    assert Group.objects.filter(tournament=tournament, round_number=1).count() == 2
    assert Match.objects.filter(group__tournament=tournament).count() == 2

    tournament.refresh_from_db()
    assert tournament.current_round == 1
    assert tournament.round_status["1"] == "ongoing"


@pytest.mark.django_db
@patch("PIL.Image.open")
@patch("os.path.exists")
def test_process_tournament_banner(mock_exists, mock_open):
    """Test tournament banner processing task with mocks"""
    mock_exists.return_value = True
    mock_image = MagicMock()
    mock_image.width = 2000
    mock_image.height = 1000
    mock_open.return_value = mock_image

    mock_resized = MagicMock()
    mock_image.resize.return_value = mock_resized

    tournament = TournamentFactory()
    result = process_tournament_banner(tournament.id, "/tmp/fake_banner.jpg")

    assert "tournament_id" in result
    mock_image.resize.assert_called()
    mock_resized.save.assert_called()
