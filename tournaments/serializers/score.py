"""
Match and MatchScore serializers.
"""
from rest_framework import serializers

from tournaments.models import Match, MatchScore


class MatchScoreSerializer(serializers.ModelSerializer):
    """Serializer for match scores"""

    team_name = serializers.CharField(source="team.team_name", read_only=True)
    team_id = serializers.IntegerField(source="team.id", read_only=True)
    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        """Get team profile picture URL"""
        try:
            # obj.team is a TournamentRegistration instance
            # obj.team.team is the Team instance
            if obj.team and hasattr(obj.team, "team") and obj.team.team:
                if obj.team.team.profile_picture:
                    return obj.team.team.profile_picture.url
        except Exception:
            # Silently handle errors to avoid breaking serialization
            pass
        return None

    class Meta:
        model = MatchScore
        fields = [
            "id",
            "team_id",
            "team_name",
            "profile_picture",
            "wins",
            "position_points",
            "kill_points",
            "total_points",
        ]
        read_only_fields = ["id", "total_points"]


class MatchSerializer(serializers.ModelSerializer):
    """Serializer for match details"""

    scores = MatchScoreSerializer(many=True, read_only=True)
    can_edit_room = serializers.SerializerMethodField()
    can_edit_scores = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    can_end = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    # 5v5-specific fields
    winner = serializers.SerializerMethodField()
    team_a = serializers.SerializerMethodField()
    team_b = serializers.SerializerMethodField()
    is_5v5_match = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            "id",
            "match_number",
            "match_id",
            "match_password",
            "status",
            "scheduled_date",
            "scheduled_time",
            "map_name",
            "started_at",
            "ended_at",
            "created_at",
            "scores",
            "can_edit_room",
            "can_edit_scores",
            "can_start",
            "can_end",
            "can_cancel",
            "winner",
            "team_a",
            "team_b",
            "is_5v5_match",
        ]
        read_only_fields = ["id", "status", "started_at", "ended_at", "created_at"]

    def get_can_edit_room(self, obj):
        return obj.can_edit_room_details()

    def get_can_edit_scores(self, obj):
        return obj.can_edit_scores()

    def get_can_start(self, obj):
        can_start, _ = obj.can_start_match()
        return can_start

    def get_can_end(self, obj):
        can_end, _ = obj.can_end_match()
        return can_end

    def get_can_cancel(self, obj):
        can_cancel, _ = obj.can_cancel_match()
        return can_cancel

    def get_winner(self, obj):
        """Return winner team info if match is completed and has a winner"""
        if obj.winner:
            return {
                "id": obj.winner.id,
                "team_name": obj.winner.team_name,
            }
        return None

    def get_team_a(self, obj):
        """Get first team in the group (for 5v5 head-to-head matches)"""
        teams = list(obj.group.teams.all()[:1])
        if teams:
            return {
                "id": teams[0].id,
                "team_name": teams[0].team_name,
            }
        return None

    def get_team_b(self, obj):
        """Get second team in the group (for 5v5 head-to-head matches)"""
        teams = list(obj.group.teams.all()[1:2])
        if teams:
            return {
                "id": teams[0].id,
                "team_name": teams[0].team_name,
            }
        return None

    def get_is_5v5_match(self, obj):
        """Check if this match belongs to a 5v5 tournament (Valorant/COD)"""
        return obj.group.tournament.is_5v5_game()
