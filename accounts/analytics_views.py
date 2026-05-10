"""
Player analytics API views
GET /api/players/analytics/stats/
GET /api/players/analytics/trend/
GET /api/players/analytics/activity/
GET /api/players/analytics/recent-results/
"""
import logging
from datetime import date, timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Team, TeamMember, TeamStatistics
from tournaments.models import Match, MatchScore, TournamentRegistration

logger = logging.getLogger("accounts")

VALID_GAMES = ["BGMI", "COD", "Valorant", "Freefire", "Scarfall"]


def _get_player_registrations(user, game=None):
    """
    Return all TournamentRegistration querysets for the authenticated player.
    Includes both:
    - Direct registrations (player registered the team as captain)
    - Member registrations (player was a team member; captain registered)
    """
    # All teams this user is/was a member of
    member_team_ids = TeamMember.objects.filter(user=user).values_list("team_id", flat=True)

    qs = TournamentRegistration.objects.filter(
        Q(player__user=user) | Q(team_id__in=member_team_ids),
        status__in=["confirmed", "pending"],
    ).distinct()

    if game and game in VALID_GAMES:
        qs = qs.filter(tournament__game_name=game)
    return qs


class PlayerAnalyticsStatsView(APIView):
    """
    Aggregate stats for the authenticated player.
    GET /api/players/analytics/stats/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")

        registrations = _get_player_registrations(request.user, game)

        # Aggregate across all MatchScore entries for these registrations
        scores_qs = MatchScore.objects.filter(team__in=registrations)
        aggregates = scores_qs.aggregate(
            matches_played=Count("id"),
            avg_kill_points=Avg("kill_points"),
            avg_position_points=Avg("position_points"),
        )

        # Tournament wins = number of completed tournaments where this player's registration
        # is the declared winner (stored in tournament.winners as {final_round: reg_id})
        total_wins = 0
        for reg in registrations.filter(tournament__status="completed").select_related("tournament"):
            t = reg.tournament
            if not t.winners:
                continue
            final_round = str(t.get_total_rounds())
            winner_reg_id = t.winners.get(final_round)
            if winner_reg_id and int(winner_reg_id) == reg.id:
                total_wins += 1

        matches_played = aggregates["matches_played"] or 0
        win_rate = round((total_wins / matches_played) * 100, 1) if matches_played > 0 else 0.0
        avg_kill_points = round(aggregates["avg_kill_points"] or 0, 1)
        avg_position_points = round(aggregates["avg_position_points"] or 0, 1)

        # Ranking: position of this player's team in their most recent tournament group's points table
        # Per flowchart spec: "There is no individual player ranking. Ranking shown = where the team
        # stands in their current tournament group's points table."
        ranking = 0
        try:
            # Find the most recent registration (completed or ongoing tournament) with match scores
            recent_reg = (
                registrations
                .filter(tournament__status__in=["completed", "ongoing"])
                .order_by("-tournament__created_at")
                .first()
            )
            if recent_reg:
                # Get the group this team belongs to in that tournament
                from tournaments.models import Group
                group = Group.objects.filter(
                    tournament=recent_reg.tournament,
                    teams=recent_reg,
                ).first()
                if group:
                    # Calculate total points per team in this group
                    group_scores = (
                        MatchScore.objects.filter(
                            match__group=group,
                        )
                        .values("team")
                        .annotate(total=Sum("total_points"))
                        .order_by("-total")
                    )
                    for idx, entry in enumerate(group_scores, 1):
                        if entry["team"] == recent_reg.id:
                            ranking = idx
                            break
        except Exception as exc:
            logger.warning(f"Failed to fetch ranking for user {request.user.id}: {exc}")

        logger.debug(
            f"Analytics stats for user {request.user.id} - game={game}, "
            f"matches={matches_played}, wins={total_wins}, rank={ranking}"
        )

        return Response(
            {
                "total_wins": total_wins,
                "matches_played": matches_played,
                "win_rate": win_rate,
                "ranking": ranking,
                "avg_kill_points": avg_kill_points,
                "avg_position_points": avg_position_points,
            }
        )


class PlayerAnalyticsTrendView(APIView):
    """
    Monthly performance trend for the last 6 months.
    GET /api/players/analytics/trend/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        registrations = _get_player_registrations(request.user, game)

        # Build the list of the last 6 months (oldest first)
        today = timezone.now().date()
        months = []
        for offset in range(5, -1, -1):
            # Subtract offset months from the first day of current month
            first_of_current = today.replace(day=1)
            # Move back `offset` months
            month_date = first_of_current
            for _ in range(offset):
                month_date = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
            months.append(month_date)

        trend = []
        for month_start in months:
            # Last day of that month
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1)

            # Filter MatchScores whose match ended_at (or created_at) falls in this month
            scores_in_month = MatchScore.objects.filter(
                team__in=registrations,
            ).filter(
                Q(match__ended_at__date__gte=month_start, match__ended_at__date__lt=month_end)
                | Q(
                    match__ended_at__isnull=True,
                    match__created_at__date__gte=month_start,
                    match__created_at__date__lt=month_end,
                )
            )

            agg = scores_in_month.aggregate(
                avg_points=Avg("total_points"),
                match_count=Count("id"),
            )

            trend.append(
                {
                    "month": month_start.strftime("%b"),
                    "avg_points": round(agg["avg_points"] or 0, 1),
                    "matches": agg["match_count"] or 0,
                }
            )

        logger.debug(f"Analytics trend for user {request.user.id} - game={game}")

        return Response({"trend": trend})


class PlayerAnalyticsActivityView(APIView):
    """
    Monthly tournament vs scrim activity counts for the last 6 months.
    GET /api/players/analytics/activity/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        registrations = _get_player_registrations(request.user, game)

        # Build the last 6 months list (oldest first)
        today = timezone.now().date()
        months = []
        for offset in range(5, -1, -1):
            first_of_current = today.replace(day=1)
            month_date = first_of_current
            for _ in range(offset):
                month_date = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
            months.append(month_date)

        activity = []
        for month_start in months:
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1)

            # Count distinct matches in this month for this player, split by event_mode
            base_qs = MatchScore.objects.filter(team__in=registrations).filter(
                Q(match__ended_at__date__gte=month_start, match__ended_at__date__lt=month_end)
                | Q(
                    match__ended_at__isnull=True,
                    match__created_at__date__gte=month_start,
                    match__created_at__date__lt=month_end,
                )
            )

            tournament_count = (
                base_qs.filter(match__group__tournament__event_mode="TOURNAMENT")
                .values("match")
                .distinct()
                .count()
            )

            scrim_count = (
                base_qs.filter(match__group__tournament__event_mode="SCRIM")
                .values("match")
                .distinct()
                .count()
            )

            activity.append(
                {
                    "month": month_start.strftime("%b"),
                    "tournaments": tournament_count,
                    "scrims": scrim_count,
                }
            )

        logger.debug(f"Analytics activity for user {request.user.id} - game={game}")

        return Response({"activity": activity})


class PlayerAnalyticsWeeklyActivityView(APIView):
    """
    Weekly tournament vs scrim activity counts for the last 8 weeks.
    GET /api/players/analytics/weekly-activity/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        registrations = _get_player_registrations(request.user, game)

        today = timezone.now().date()
        # Start from the Monday of the current week
        current_monday = today - timedelta(days=today.weekday())

        weeks = []
        for offset in range(7, -1, -1):
            week_start = current_monday - timedelta(weeks=offset)
            week_end = week_start + timedelta(days=7)
            weeks.append((week_start, week_end))

        activity = []
        for week_start, week_end in weeks:
            base_qs = MatchScore.objects.filter(team__in=registrations).filter(
                Q(match__ended_at__date__gte=week_start, match__ended_at__date__lt=week_end)
                | Q(
                    match__ended_at__isnull=True,
                    match__created_at__date__gte=week_start,
                    match__created_at__date__lt=week_end,
                )
            )

            tournament_count = (
                base_qs.filter(match__group__tournament__event_mode="TOURNAMENT")
                .values("match").distinct().count()
            )
            scrim_count = (
                base_qs.filter(match__group__tournament__event_mode="SCRIM")
                .values("match").distinct().count()
            )

            activity.append({
                "week": week_start.strftime("%d %b"),
                "tournaments": tournament_count,
                "scrims": scrim_count,
            })

        return Response({"activity": activity})


class PlayerAnalyticsWeeklyTrendView(APIView):
    """
    Weekly performance trend (avg total points) for the last 8 weeks.
    GET /api/players/analytics/weekly-trend/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        registrations = _get_player_registrations(request.user, game)

        today = timezone.now().date()
        current_monday = today - timedelta(days=today.weekday())

        trend = []
        for offset in range(7, -1, -1):
            week_start = current_monday - timedelta(weeks=offset)
            week_end = week_start + timedelta(days=7)

            scores_in_week = MatchScore.objects.filter(team__in=registrations).filter(
                Q(match__ended_at__date__gte=week_start, match__ended_at__date__lt=week_end)
                | Q(
                    match__ended_at__isnull=True,
                    match__created_at__date__gte=week_start,
                    match__created_at__date__lt=week_end,
                )
            )

            agg = scores_in_week.aggregate(
                avg_points=Avg("total_points"),
                match_count=Count("id"),
            )

            trend.append({
                "week": week_start.strftime("%d %b"),
                "avg_points": round(agg["avg_points"] or 0, 1),
                "matches": agg["match_count"] or 0,
            })

        return Response({"trend": trend})


class PlayerAnalyticsRecentResultsView(APIView):
    """
    Last 10 match results for the authenticated player.
    GET /api/players/analytics/recent-results/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        registrations = _get_player_registrations(request.user, game)

        recent_scores = (
            MatchScore.objects.filter(team__in=registrations)
            .select_related(
                "match",
                "match__group",
                "match__group__tournament",
                "team",
            )
            .order_by("-match__created_at")[:10]
        )

        results = []
        for score in recent_scores:
            match = score.match
            tournament = match.group.tournament

            # Calculate placement: count how many other scores in the same match
            # have strictly higher total_points, then add 1
            higher_count = MatchScore.objects.filter(
                match=match,
                total_points__gt=score.total_points,
            ).count()
            placement = higher_count + 1

            # Use ended_at if available, otherwise fall back to created_at
            match_date = match.ended_at.date() if match.ended_at else match.created_at.date()

            results.append(
                {
                    "tournament_title": tournament.title,
                    "game_name": tournament.game_name,
                    "match_number": match.match_number,
                    "placement": placement,
                    "total_points": score.total_points,
                    "kills": score.kill_points,
                    "date": str(match_date),
                }
            )

        logger.debug(
            f"Analytics recent results for user {request.user.id} - game={game}, count={len(results)}"
        )

        return Response({"results": results})


class PlayerTeamAnalyticsView(APIView):
    """
    Team analytics for the authenticated player, scoped to their personal registrations.
    Returns stats for all teams the player was/is part of (current + past).
    Each team shows Team Overall stats (from TeamStatistics) and My Contribution
    (computed from TournamentRegistration rows where the player was personally registered).
    GET /api/players/analytics/team-stats/?game=BGMI
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        game = request.query_params.get("game")
        user = request.user

        # All teams this user has been a member of (current or past, via TeamMember or captain)
        member_team_ids = list(
            TeamMember.objects.filter(user=user).values_list("team_id", flat=True)
        )
        captain_team_ids = list(
            Team.objects.filter(captain=user).values_list("id", flat=True)
        )
        current_team_ids = set(member_team_ids) | set(captain_team_ids)

        # All teams the user ever personally registered with (selected to play, not just a team member).
        # Uses team_members JSON to check explicit selection so we don't include teams where the
        # player is a TeamMember but was never picked for any actual registration.
        try:
            _pp_id = user.playerprofile.id
        except Exception:
            _pp_id = None

        captain_reg_team_ids = list(
            TournamentRegistration.objects.filter(
                player__user=user,
                status__in=["confirmed", "pending"],
            ).values_list("team_id", flat=True).distinct()
        )
        member_reg_team_ids = []
        if _pp_id:
            for reg in TournamentRegistration.objects.filter(
                team_id__in=member_team_ids,
                status__in=["confirmed", "pending"],
            ).only("id", "team_id", "team_members"):
                members = reg.team_members or []
                if any(
                    m.get("player_id") == _pp_id and m.get("is_registered")
                    for m in members
                ):
                    member_reg_team_ids.append(reg.team_id)

        reg_team_ids = list(set(captain_reg_team_ids) | set(member_reg_team_ids))

        all_team_ids = set(reg_team_ids)
        if not all_team_ids:
            return Response([])

        teams = Team.objects.filter(id__in=all_team_ids)
        today = timezone.now().date()
        results = []

        # Player profile ID used to check team_members JSON field
        try:
            player_profile_id = user.playerprofile.id
        except Exception:
            player_profile_id = None

        for team in teams:
            # All registrations for this team with confirmed/pending status
            all_regs_for_team = TournamentRegistration.objects.filter(
                team=team,
                status__in=["confirmed", "pending"],
            )
            if game and game in VALID_GAMES:
                all_regs_for_team = all_regs_for_team.filter(tournament__game_name=game)

            # Filter to registrations where this player was personally selected to play.
            # Checks: (1) user was the captain who registered, OR
            # (2) user appears in team_members JSON with is_registered=True.
            # This prevents inflating stats from registrations the player wasn't part of
            # even if they're a TeamMember of the team.
            my_reg_ids = []
            for reg in all_regs_for_team.select_related("player__user"):
                if reg.player_id and reg.player.user_id == user.id:
                    my_reg_ids.append(reg.id)
                elif player_profile_id:
                    members = reg.team_members or []
                    if any(
                        m.get("player_id") == player_profile_id and m.get("is_registered")
                        for m in members
                    ):
                        my_reg_ids.append(reg.id)

            if not my_reg_ids:
                continue

            my_regs = TournamentRegistration.objects.filter(id__in=my_reg_ids)

            # ── My Contribution ───────────────────────────────────────────
            scores_qs = MatchScore.objects.filter(team__in=my_regs)
            agg = scores_qs.aggregate(
                matches_played=Count("id"),
                total_points_earned=Sum("total_points"),
            )
            matches_played = agg["matches_played"] or 0
            total_points_earned = agg["total_points_earned"] or 0

            my_wins = 0
            tournaments_played = my_regs.count()
            for reg in my_regs.filter(tournament__status="completed").select_related("tournament"):
                t = reg.tournament
                if not t.winners:
                    continue
                final_round = str(t.get_total_rounds())
                winner_reg_id = t.winners.get(final_round)
                if winner_reg_id and int(winner_reg_id) == reg.id:
                    my_wins += 1

            win_rate = round((my_wins / tournaments_played) * 100, 1) if tournaments_played > 0 else 0.0

            # ── Team Overall (from TeamStatistics) ────────────────────────
            team_overall = {}
            try:
                ts_qs = TeamStatistics.objects.filter(team=team)
                if game and game in VALID_GAMES:
                    ts_qs = ts_qs.filter(game_name=game)
                else:
                    ts_qs = ts_qs.filter(game_name="ALL")
                ts = ts_qs.first()
                if ts:
                    team_overall = {
                        "rank": ts.rank,
                        "tournament_rank": ts.tournament_rank,
                        "scrim_rank": ts.scrim_rank,
                        "total_points": ts.total_points,
                        "tournament_wins": ts.tournament_wins,
                        "matches_played": ts.matches_played,
                        "tournament_matches_played": ts.tournament_matches_played,
                        "scrim_matches_played": ts.scrim_matches_played,
                    }
            except Exception as exc:
                logger.warning(f"TeamStatistics fetch failed for team {team.id}: {exc}")

            # ── Performance Trend (last 6 months, my registrations only) ──
            months = []
            for offset in range(5, -1, -1):
                first_of_current = today.replace(day=1)
                month_date = first_of_current
                for _ in range(offset):
                    month_date = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
                months.append(month_date)

            trend = []
            for month_start in months:
                if month_start.month == 12:
                    month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
                else:
                    month_end = month_start.replace(month=month_start.month + 1, day=1)

                scores_in_month = MatchScore.objects.filter(team__in=my_regs).filter(
                    Q(match__ended_at__date__gte=month_start, match__ended_at__date__lt=month_end)
                    | Q(
                        match__ended_at__isnull=True,
                        match__created_at__date__gte=month_start,
                        match__created_at__date__lt=month_end,
                    )
                )
                month_agg = scores_in_month.aggregate(
                    avg_points=Avg("total_points"),
                    match_count=Count("id"),
                )
                trend.append({
                    "month": month_start.strftime("%b"),
                    "avg_points": round(month_agg["avg_points"] or 0, 1),
                    "matches": month_agg["match_count"] or 0,
                })

            # ── Recent Results (last 10, my registrations only) ───────────
            recent_scores = (
                MatchScore.objects.filter(team__in=my_regs)
                .select_related("match", "match__group", "match__group__tournament")
                .order_by("-match__created_at")[:10]
            )
            recent_results = []
            for score in recent_scores:
                match = score.match
                tournament = match.group.tournament
                higher_count = MatchScore.objects.filter(
                    match=match, total_points__gt=score.total_points
                ).count()
                placement = higher_count + 1
                match_date = match.ended_at.date() if match.ended_at else match.created_at.date()
                recent_results.append({
                    "tournament_title": tournament.title,
                    "game_name": tournament.game_name,
                    "match_number": match.match_number,
                    "placement": placement,
                    "total_points": score.total_points,
                    "kills": score.kill_points,
                    "date": str(match_date),
                })

            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_current_member": team.id in current_team_ids,
                "team_overall": team_overall,
                "my_contribution": {
                    "tournaments_played": tournaments_played,
                    "matches_played": matches_played,
                    "wins": my_wins,
                    "win_rate": win_rate,
                    "total_points_earned": total_points_earned,
                },
                "trend": trend,
                "recent_results": recent_results,
            })

        # Sort: current members first, then alphabetically
        results.sort(key=lambda t: (0 if t["is_current_member"] else 1, t["team_name"]))
        return Response(results)
