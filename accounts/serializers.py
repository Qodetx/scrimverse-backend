from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.db.models import Avg, Q, Sum

from rest_framework import serializers

from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, TeamStatistics, User
from accounts.tasks import update_host_rating_cache
from tournaments.models import HostRating, Tournament, TournamentRegistration


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "user_type",
            "phone_number",
            "profile_picture",
            "username_change_count",
            "last_username_change",
            "is_email_verified",
            "created_at",
        )
        read_only_fields = ("id", "username_change_count", "last_username_change", "is_email_verified", "created_at")


class PlayerProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    current_team = serializers.SerializerMethodField()
    matches_played = serializers.SerializerMethodField()
    tournament_wins = serializers.SerializerMethodField()
    scrim_wins = serializers.SerializerMethodField()
    global_rank = serializers.SerializerMethodField()
    tournament_rank = serializers.SerializerMethodField()
    scrim_rank = serializers.SerializerMethodField()
    invitation_status = serializers.SerializerMethodField()

    class Meta:
        model = PlayerProfile
        fields = (
            "id",
            "user",
            "preferred_games",
            "bio",
            "total_tournaments_participated",
            "total_wins",
            "current_team",
            "matches_played",
            "tournament_wins",
            "scrim_wins",
            "global_rank",
            "tournament_rank",
            "scrim_rank",
            "invitation_status",
        )

    def get_invitation_status(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        # Check if requesting user is a captain of ANY team
        # (Though usually they only have one)
        managed_team_ids = Team.objects.filter(captain=request.user).values_list("id", flat=True)
        if not managed_team_ids:
            return None

        # Check for pending invitation from any of those teams to this player
        invitation = TeamJoinRequest.objects.filter(
            team_id__in=managed_team_ids, player=obj.user, request_type="invite", status="pending"
        ).first()

        return invitation.status if invitation else None

    def get_current_team(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership:
            team = membership.team
            members = TeamMember.objects.filter(team=team)
            return {
                "id": team.id,
                "name": team.name,
                "profile_picture": team.profile_picture.url if team.profile_picture else None,
                "is_captain": membership.is_captain,
                "members": [
                    {
                        "id": m.user.id if m.user else None,
                        "username": m.username,
                        "is_captain": m.is_captain,
                        "user": {
                            "profile_picture": m.user.profile_picture.url
                            if m.user and m.user.profile_picture
                            else None,
                        }
                        if m.user
                        else None,
                    }
                    for m in members
                ],
            }
        return None

    def get_matches_played(self, obj):
        """
        Count the number of tournaments and scrims the player has participated in.
        Includes both individual registrations and team registrations.
        """
        # Get all team IDs the user is part of
        team_ids = TeamMember.objects.filter(user=obj.user).values_list("team_id", flat=True)

        # Count confirmed registrations (where player is registrant OR team is player's team)
        registrations_count = (
            TournamentRegistration.objects.filter(Q(player=obj) | Q(team_id__in=team_ids), status="confirmed")
            .distinct()
            .count()
        )

        return registrations_count

    def get_tournament_wins(self, obj):
        # Get game filter from context (default: 'ALL')
        game_filter = self.context.get('game_filter', 'ALL')
        
        # Prefer membership where they are captain, or just the first one
        memberships = TeamMember.objects.filter(user=obj.user).select_related("team")
        max_wins = 0
        for m in memberships:
            try:
                if game_filter == 'ALL':
                    # Aggregate across all game-specific stats (exclude 'ALL' row)
                    total = m.team.statistics_by_game.exclude(game_name='ALL').aggregate(
                        total_wins=Sum('tournament_wins')
                    )['total_wins'] or 0
                    max_wins = max(max_wins, total)
                else:
                    # Get game-specific stats
                    stats = m.team.statistics_by_game.filter(game_name=game_filter).first()
                    if stats:
                        max_wins = max(max_wins, stats.tournament_wins)
            except Exception:
                continue
        return max_wins

    def get_scrim_wins(self, obj):
        # Get game filter from context (default: 'ALL')
        game_filter = self.context.get('game_filter', 'ALL')
        
        memberships = TeamMember.objects.filter(user=obj.user).select_related("team")
        max_wins = 0
        for m in memberships:
            try:
                if game_filter == 'ALL':
                    # Aggregate across all game-specific stats (exclude 'ALL' row)
                    total = m.team.statistics_by_game.exclude(game_name='ALL').aggregate(
                        total_wins=Sum('scrim_wins')
                    )['total_wins'] or 0
                    max_wins = max(max_wins, total)
                else:
                    # Get game-specific stats
                    stats = m.team.statistics_by_game.filter(game_name=game_filter).first()
                    if stats:
                        max_wins = max(max_wins, stats.scrim_wins)
            except Exception:
                continue
        return max_wins

    def get_global_rank(self, obj):
        # Get game filter from context (default: 'ALL')
        game_filter = self.context.get('game_filter', 'ALL')
        
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership:
            try:
                # For ranks, always use the stored rank from the 'ALL' or specific game row
                if game_filter == 'ALL':
                    # For ALL, use the aggregate rank stored in 'ALL' row
                    stats = membership.team.statistics_by_game.filter(game_name='ALL').first()
                else:
                    # For specific game, use that game's rank
                    stats = membership.team.statistics_by_game.filter(game_name=game_filter).first()
                if stats:
                    return stats.rank
            except Exception:
                pass
        return None

    def get_tournament_rank(self, obj):
        # Get game filter from context (default: 'ALL')
        game_filter = self.context.get('game_filter', 'ALL')
        
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership:
            try:
                # For ranks, use the stored rank from the 'ALL' or specific game row
                if game_filter == 'ALL':
                    stats = membership.team.statistics_by_game.filter(game_name='ALL').first()
                else:
                    stats = membership.team.statistics_by_game.filter(game_name=game_filter).first()
                if stats:
                    return stats.tournament_rank
            except Exception:
                pass
        return None

    def get_scrim_rank(self, obj):
        # Get game filter from context (default: 'ALL')
        game_filter = self.context.get('game_filter', 'ALL')
        
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership:
            try:
                # For ranks, use the stored rank from the 'ALL' or specific game row
                if game_filter == 'ALL':
                    stats = membership.team.statistics_by_game.filter(game_name='ALL').first()
                else:
                    stats = membership.team.statistics_by_game.filter(game_name=game_filter).first()
                if stats:
                    return stats.scrim_rank
            except Exception:
                pass
        return None


class HostProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    total_participants = serializers.SerializerMethodField()
    prize_pool_distributed = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    total_tournaments_hosted = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    has_user_rated = serializers.SerializerMethodField()

    class Meta:
        model = HostProfile
        fields = (
            "id",
            "user",
            "bio",
            "website",
            "total_tournaments_hosted",
            "rating",
            "total_ratings",
            "verified",
            "aadhar_card_front",
            "aadhar_card_back",
            "aadhar_uploaded_at",
            "verification_status",
            "verification_notes",
            "total_participants",
            "prize_pool_distributed",
            "success_rate",
            "average_rating",
            "has_user_rated",
        )
        read_only_fields = (
            "id",
            "rating",
            "total_ratings",
            "verified",
            "aadhar_uploaded_at",
            "verification_status",
            "verification_notes",
        )

    def get_total_tournaments_hosted(self, obj):
        return Tournament.objects.filter(host=obj).count()

    def get_total_participants(self, obj):
        return TournamentRegistration.objects.filter(tournament__host=obj, status="confirmed").count()

    def get_prize_pool_distributed(self, obj):
        return Tournament.objects.filter(host=obj, status="completed").aggregate(total=Sum("prize_pool"))["total"] or 0

    def get_success_rate(self, obj):
        total = Tournament.objects.filter(host=obj).count()
        if total == 0:
            return 100
        completed = Tournament.objects.filter(host=obj, status="completed").count()
        return round((completed / total) * 100)

    def get_average_rating(self, obj):
        # Try cache first (populated by Celery task)
        cached = cache.get(f"host:rating:{obj.id}")
        if cached:
            return cached["average_rating"]

        # Fallback: calculate now and trigger cache update
        update_host_rating_cache.delay(obj.id)

        avg = HostRating.objects.filter(host=obj).aggregate(avg=Avg("rating"))["avg"]
        return round(avg, 1) if avg else 0.0

    def get_has_user_rated(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        if request.user.user_type != "player":
            return False

        try:
            player_profile = request.user.player_profile
            has_rated = HostRating.objects.filter(host=obj, player=player_profile).exists()
            print(f"DEBUG: User {request.user.id} (player {player_profile.id}) has_rated host {obj.id}: {has_rated}")
            return has_rated
        except Exception as e:
            print(f"ERROR in has_user_rated: {e}")
            return False


class PlayerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(max_length=10, required=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        # Remove password2 and profile fields
        validated_data.pop("password2")

        # Create user
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="player",
            phone_number=validated_data.get("phone_number", ""),
        )

        # Create player profile
        PlayerProfile.objects.create(user=user)

        return user


class HostRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone_number = serializers.CharField(max_length=10, required=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "password2", "phone_number")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def validate_phone_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        if len(value) != 10:
            raise serializers.ValidationError("Phone number must be exactly 10 digits long.")
        return value

    def create(self, validated_data):
        # Remove password2 and profile fields
        validated_data.pop("password2")

        # Create user
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            user_type="host",
            phone_number=validated_data.get("phone_number"),
        )

        # Create host profile
        HostProfile.objects.create(user=user)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    user_type = serializers.ChoiceField(choices=["player", "host"], required=True)


class TeamMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = TeamMember
        fields = ("id", "username", "user", "is_captain")


class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(many=True, read_only=True)
    captain_details = UserSerializer(source="captain", read_only=True)
    win_rate = serializers.ReadOnlyField()
    pending_requests_count = serializers.SerializerMethodField()
    user_request_status = serializers.SerializerMethodField()
    stats_by_game = serializers.SerializerMethodField()
    overall_stats = serializers.SerializerMethodField()

    def get_pending_requests_count(self, obj):
        return obj.join_requests.filter(status="pending").count()

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