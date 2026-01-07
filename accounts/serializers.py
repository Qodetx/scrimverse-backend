from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from .models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, TeamStatistics, User


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
            "created_at",
        )
        read_only_fields = ("id", "username_change_count", "last_username_change", "created_at")


class PlayerProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    current_team = serializers.SerializerMethodField()
    matches_played = serializers.SerializerMethodField()
    tournament_wins = serializers.SerializerMethodField()
    scrim_wins = serializers.SerializerMethodField()
    global_rank = serializers.SerializerMethodField()
    tournament_rank = serializers.SerializerMethodField()
    scrim_rank = serializers.SerializerMethodField()

    class Meta:
        model = PlayerProfile
        fields = "__all__"

    def get_current_team(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership:
            return {"id": membership.team.id, "name": membership.team.name}
        return None

    def get_matches_played(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            # In our data script we aggregate these, but for now we can sum position points if needed
            # For simplicity, let's look at total_matches on the team scale
            return membership.team.total_matches
        return 0

    def get_tournament_wins(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            return membership.team.statistics.tournament_wins
        return 0

    def get_scrim_wins(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            return membership.team.statistics.scrim_wins
        return 0

    def get_global_rank(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            return membership.team.statistics.rank
        return None

    def get_tournament_rank(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            return membership.team.statistics.tournament_rank
        return None

    def get_scrim_rank(self, obj):
        membership = TeamMember.objects.filter(user=obj.user).first()
        if membership and hasattr(membership.team, "statistics"):
            return membership.team.statistics.scrim_rank
        return None


class HostProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = HostProfile
        fields = "__all__"


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
    class Meta:
        model = TeamMember
        fields = ("id", "username", "user", "is_captain")


class TeamSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(many=True, read_only=True)
    captain_details = UserSerializer(source="captain", read_only=True)
    win_rate = serializers.ReadOnlyField()
    pending_requests_count = serializers.SerializerMethodField()
    user_request_status = serializers.SerializerMethodField()

    def get_pending_requests_count(self, obj):
        return obj.join_requests.filter(status="pending").count()

    def get_user_request_status(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            join_request = obj.join_requests.filter(player=request.user).first()
            return join_request.status if join_request else None
        return None

    class Meta:
        model = Team
        fields = (
            "id",
            "name",
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
            "tournament_wins",
            "total_position_points",
            "total_kill_points",
            "total_points",
            "last_updated",
        )
