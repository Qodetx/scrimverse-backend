"""
Team, TeamMember, TeamJoinRequest, and TeamStatistics serializers.
"""
from django.db.models import Sum

from rest_framework import serializers

from accounts.models import Team, TeamJoinRequest, TeamMember, TeamStatistics
from accounts.serializers.user import UserSerializer


class TeamMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = TeamMember
        fields = (
            "id", "username", "user", "is_captain", "role",
            "is_temporary", "conversion_deadline",
        )


class TeamSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()  # Changed from TeamMemberSerializer to custom method
    captain_details = UserSerializer(source="captain", read_only=True)
    win_rate = serializers.ReadOnlyField()
    pending_requests_count = serializers.SerializerMethodField()
    user_request_status = serializers.SerializerMethodField()
    stats_by_game = serializers.SerializerMethodField()
    overall_stats = serializers.SerializerMethodField()
    linked_tournament_info = serializers.SerializerMethodField()
    is_temporary_for_me = serializers.SerializerMethodField()
    my_conversion_deadline = serializers.SerializerMethodField()
    invited_members = serializers.SerializerMethodField()

    def get_members(self, obj):
        """Get all team members INCLUDING the captain, excluding captain from TeamMember list to avoid duplication"""
        members_list = []

        # Add captain first as a unified entry
        captain_pic = obj.captain.profile_picture.url if obj.captain.profile_picture else None
        captain_member = {
            'id': obj.captain.id,
            'username': obj.captain.username,
            'email': obj.captain.email,
            'profile_picture': captain_pic,
            'role': 'Captain',
            'is_captain': True,
            'join_date': obj.created_at.isoformat() if obj.created_at else None,
        }
        members_list.append(captain_member)

        # Add non-captain team members only (exclude captain's TeamMember entry to avoid showing them twice)
        other_members = obj.members.exclude(username=obj.captain.username)
        other_members_data = TeamMemberSerializer(other_members, many=True).data
        # Force is_captain=False for all non-captain members (stale flag after captaincy transfer)
        for m in other_members_data:
            m['is_captain'] = False
        members_list.extend(other_members_data)

        return members_list

    def get_pending_requests_count(self, obj):
        return obj.join_requests.filter(status="pending", request_type="request").count()

    def get_user_request_status(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            join_request = obj.join_requests.filter(player=request.user).first()
            return join_request.status if join_request else None
        return None

    def get_stats_by_game(self, obj):
        """Get game-specific statistics breakdown (excluding 'ALL')"""
        stats_dict = {}
        game_stats = obj.statistics_by_game.exclude(game_name='ALL')

        for stats in game_stats:
            stats_dict[stats.game_name] = {
                'tournament_wins': stats.tournament_wins,
                'scrim_wins': stats.scrim_wins,
                'tournament_points': stats.tournament_position_points + stats.tournament_kill_points,
                'scrim_points': stats.scrim_position_points + stats.scrim_kill_points,
                'rank': stats.rank,
                'tournament_rank': stats.tournament_rank,
                'scrim_rank': stats.scrim_rank,
            }

        return stats_dict

    def get_linked_tournament_info(self, obj):
        if obj.linked_tournament:
            return {
                "id": obj.linked_tournament.id,
                "title": obj.linked_tournament.title,
                "registration_end": obj.linked_tournament.registration_end,
            }
        return None

    def _current_user_membership(self, obj):
        """Returns the requesting user's TeamMember row on this team, or None."""
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        return obj.members.filter(user=request.user).first()

    def get_is_temporary_for_me(self, obj):
        """
        Whether this team should be presented as temporary to the *current user*.

        - Legacy team-level flag: True for everyone if Team.is_temporary is True.
        - Per-member flag: True if the current user's TeamMember has is_temporary=True.
        """
        if getattr(obj, "is_temporary", False):
            return True
        membership = self._current_user_membership(obj)
        return bool(membership and membership.is_temporary)

    def get_my_conversion_deadline(self, obj):
        """The current user's per-member 48h conversion deadline, if any."""
        membership = self._current_user_membership(obj)
        if membership and membership.is_temporary:
            return membership.conversion_deadline
        # Fall back to legacy team-level deadline if team itself is temp
        if getattr(obj, "is_temporary", False):
            return obj.conversion_deadline
        return None

    def get_invited_members(self, obj):
        """
        Outgoing invites for this team that are still actionable — pending,
        rejected, or expired. Accepted invites are excluded because the
        invitee is already a real TeamMember and shows up in `members`.

        Used by the Teams tab so the captain can see at a glance who they
        invited (and resend if needed) instead of panicking when the team
        looks empty after a fresh registration.
        """
        invites = obj.join_requests.filter(
            request_type="invite",
            status__in=["pending", "rejected", "expired"],
        ).select_related("player").order_by("created_at")

        result = []
        for inv in invites:
            # Identifier is what the captain typed — phone, email, or username
            if inv.invite_type == "phone":
                identifier = inv.phone_number or ""
                display_name = inv.phone_number or ""
            elif inv.invite_type == "email":
                identifier = inv.invited_email or ""
                display_name = inv.invited_email or ""
            elif inv.invite_type == "username":
                identifier = inv.player.username if inv.player else ""
                display_name = identifier
            else:  # link
                identifier = inv.invite_token or ""
                display_name = "Invite link"

            result.append({
                "id": inv.id,
                "invite_type": inv.invite_type,
                "identifier": identifier,
                "display_name": display_name,
                "status": inv.status,
                "created_at": inv.created_at,
                "expires_at": inv.invite_expires_at,
            })
        return result

    def get_overall_stats(self, obj):
        """Get aggregate statistics across all games - aggregate from game-specific rows"""
        # Aggregate wins and points from all game-specific rows (exclude 'ALL')
        aggregated = obj.statistics_by_game.exclude(game_name='ALL').aggregate(
            total_tournament_wins=Sum('tournament_wins'),
            total_scrim_wins=Sum('scrim_wins'),
            total_tournament_pos=Sum('tournament_position_points'),
            total_tournament_kills=Sum('tournament_kill_points'),
            total_scrim_pos=Sum('scrim_position_points'),
            total_scrim_kills=Sum('scrim_kill_points'),
            total_points_sum=Sum('total_points'),
            total_matches=Sum('matches_played'),
            total_tournament_matches=Sum('tournament_matches_played'),
            total_scrim_matches=Sum('scrim_matches_played'),
        )

        # Get ranks from the 'ALL' row (ranks are calculated separately)
        all_stats = obj.statistics_by_game.filter(game_name='ALL').first()

        tournament_points = (aggregated['total_tournament_pos'] or 0) + (aggregated['total_tournament_kills'] or 0)
        scrim_points = (aggregated['total_scrim_pos'] or 0) + (aggregated['total_scrim_kills'] or 0)
        total_kills = (aggregated['total_tournament_kills'] or 0) + (aggregated['total_scrim_kills'] or 0)
        tournament_kills = aggregated['total_tournament_kills'] or 0
        scrim_kills = aggregated['total_scrim_kills'] or 0
        matches_played = aggregated['total_matches'] or 0
        tournament_matches = aggregated['total_tournament_matches'] or 0
        scrim_matches = aggregated['total_scrim_matches'] or 0

        # K/D as kills-per-match (true K/D requires deaths tracking which we
        # don't store today). Surfaced on team search cards so users can
        # quickly compare team performance.
        kd_ratio = round(total_kills / matches_played, 2) if matches_played > 0 else 0

        # "Recent" = matches the team played in the last 30 days, counted
        # via MatchScore rows linked to the team's TournamentRegistration
        # records. Used by team search results to indicate activity.
        recent_matches_count = 0
        try:
            from datetime import timedelta
            from django.utils import timezone
            from tournaments.models import MatchScore
            cutoff = timezone.now() - timedelta(days=30)
            recent_matches_count = MatchScore.objects.filter(
                team__team=obj,
                match__ended_at__gte=cutoff,
            ).values('match_id').distinct().count()
        except Exception:
            recent_matches_count = 0

        return {
            'tournament_wins': aggregated['total_tournament_wins'] or 0,
            'scrim_wins': aggregated['total_scrim_wins'] or 0,
            'tournament_points': tournament_points,
            'scrim_points': scrim_points,
            'total_points': aggregated['total_points_sum'] or 0,
            'rank': all_stats.rank if all_stats else 0,
            'tournament_rank': all_stats.tournament_rank if all_stats else 0,
            'scrim_rank': all_stats.scrim_rank if all_stats else 0,
            'total_kills': total_kills,
            'tournament_kills': tournament_kills,
            'scrim_kills': scrim_kills,
            'matches_played': matches_played,
            'tournament_matches': tournament_matches,
            'scrim_matches': scrim_matches,
            'kd_ratio': kd_ratio,
            'recent_matches': recent_matches_count,
        }

    class Meta:
        model = Team
        fields = (
            "id",
            "name",
            "description",
            "profile_picture",
            "captain",
            "captain_details",
            "members",
            "created_at",
            "is_temporary",
            "conversion_deadline",
            "is_temporary_for_me",
            "my_conversion_deadline",
            "invited_members",
            "linked_tournament_info",
            "game",
            "total_matches",
            "wins",
            "losses",
            "win_rate",
            "pending_requests_count",
            "user_request_status",
            "stats_by_game",
            "overall_stats",
        )
        read_only_fields = ("id", "created_at", "captain")


class TeamJoinRequestSerializer(serializers.ModelSerializer):
    player_details = UserSerializer(source="player", read_only=True)
    team_details = TeamSerializer(source="team", read_only=True)

    class Meta:
        model = TeamJoinRequest
        fields = "__all__"
        read_only_fields = ("player", "status", "created_at", "updated_at")


class TeamStatisticsSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_id = serializers.IntegerField(source="team.id", read_only=True)

    class Meta:
        model = TeamStatistics
        fields = (
            "team_id",
            "team_name",
            "rank",
            "tournament_rank",
            "scrim_rank",
            "tournament_wins",
            "total_position_points",
            "total_kill_points",
            "total_points",
            "matches_played",
            "tournament_matches_played",
            "scrim_matches_played",
            "last_updated",
        )


# ============================================================================
# TEAM INVITE SERIALIZER (Invite-Based Registration Flow)
# ============================================================================


class TeamInviteDetailSerializer(serializers.Serializer):
    """
    Public serializer for displaying team invite details on the frontend.
    Used by guests to see who invited them before accepting/declining.
    """

    team_name = serializers.CharField(read_only=True)
    captain_name = serializers.CharField(read_only=True)
    tournament_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    invited_email = serializers.EmailField(read_only=True)
    invite_expires_at = serializers.DateTimeField(read_only=True)
