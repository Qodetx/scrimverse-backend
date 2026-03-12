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
        fields = ("id", "username", "user", "is_captain")


class TeamSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()  # Changed from TeamMemberSerializer to custom method
    captain_details = UserSerializer(source="captain", read_only=True)
    win_rate = serializers.ReadOnlyField()
    pending_requests_count = serializers.SerializerMethodField()
    user_request_status = serializers.SerializerMethodField()
    stats_by_game = serializers.SerializerMethodField()
    overall_stats = serializers.SerializerMethodField()

    def get_members(self, obj):
        """Get all team members INCLUDING the captain, excluding captain from TeamMember list to avoid duplication"""
        members_list = []

        # Add captain first as a unified entry
        captain_member = {
            'id': obj.captain.id,
            'username': obj.captain.username,
            'email': obj.captain.email,
            'role': 'captain',
            'is_captain': True,
            'join_date': obj.created_at.isoformat() if obj.created_at else None,
        }
        members_list.append(captain_member)

        # Add non-captain team members only (exclude captain's TeamMember entry to avoid showing them twice)
        other_members = obj.members.exclude(
            username=obj.captain.username
        )
        other_members_data = TeamMemberSerializer(other_members, many=True).data
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
        )

        # Get ranks from the 'ALL' row (ranks are calculated separately)
        all_stats = obj.statistics_by_game.filter(game_name='ALL').first()

        tournament_points = (aggregated['total_tournament_pos'] or 0) + (aggregated['total_tournament_kills'] or 0)
        scrim_points = (aggregated['total_scrim_pos'] or 0) + (aggregated['total_scrim_kills'] or 0)

        return {
            'tournament_wins': aggregated['total_tournament_wins'] or 0,
            'scrim_wins': aggregated['total_scrim_wins'] or 0,
            'tournament_points': tournament_points,
            'scrim_points': scrim_points,
            'total_points': aggregated['total_points_sum'] or 0,
            'rank': all_stats.rank if all_stats else 0,
            'tournament_rank': all_stats.tournament_rank if all_stats else 0,
            'scrim_rank': all_stats.scrim_rank if all_stats else 0,
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
