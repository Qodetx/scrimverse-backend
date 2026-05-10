"""
Tournament serializers: TournamentSerializer and TournamentListSerializer.
"""
import json

from django.conf import settings

from rest_framework import serializers

from accounts.serializers import HostProfileSerializer
from tournaments.models import Tournament, TournamentSponsor


class TournamentSponsorSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(max_length=None, use_url=True, required=False, allow_null=True)
    website_url = serializers.URLField(required=False, allow_blank=True, default="")

    class Meta:
        model = TournamentSponsor
        fields = ("id", "name", "sponsor_type", "logo", "website_url", "display_order")


class TournamentSerializer(serializers.ModelSerializer):
    host = HostProfileSerializer(read_only=True)
    host_id = serializers.IntegerField(write_only=True, required=False)
    banner_image = serializers.ImageField(
        max_length=None, use_url=True, required=False, allow_null=True, allow_empty_file=True
    )
    tournament_file = serializers.FileField(
        max_length=None, use_url=True, required=False, allow_null=True, allow_empty_file=True
    )
    rounds = serializers.JSONField(required=False)
    placement_points = serializers.JSONField(required=False)
    prize_distribution = serializers.JSONField(required=False)
    round_dates = serializers.JSONField(required=False)

    # 5v5-specific fields
    is_5v5 = serializers.SerializerMethodField()
    requires_password = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = "__all__"
        read_only_fields = (
            "current_participants",
            "created_at",
            "updated_at",
            "host",
            "plan_price",
            "is_featured",
        )

    def validate_banner_image(self, value):
        """Validate banner image size (max 5MB) and premium plan requirement"""
        if value and value.size > 5 * 1024 * 1024:  # 5MB
            raise serializers.ValidationError("Banner image size should not exceed 5MB")

        return value

    def validate_max_participants(self, value):
        """Validate max participants based on plan type and event mode"""
        data = self.initial_data
        event_mode = data.get("event_mode", "TOURNAMENT")

        if event_mode == "SCRIM" and value > 25:
            raise serializers.ValidationError("Scrims allow maximum 25 teams.")

        plan_type = data.get("plan_type", "basic")
        if plan_type == "basic" and value > 100:
            raise serializers.ValidationError(
                "Basic plan allows maximum 100 teams. Upgrade to Featured or Premium plan for unlimited teams."
            )
        return value

    def validate_rounds(self, value):
        """Validate rounds structure"""
        event_mode = self.initial_data.get("event_mode", "TOURNAMENT")

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for rounds")

        if event_mode == "SCRIM":
            # For Scrims, we force 1 round
            max_teams = self.initial_data.get("max_participants")
            if not max_teams and self.instance:
                max_teams = self.instance.max_participants

            return [{"round": 1, "max_teams": int(max_teams) if max_teams else 25, "qualifying_teams": 0}]

        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one round is required")

        for i, round_data in enumerate(value):
            if "round" not in round_data:
                raise serializers.ValidationError(f"Round {i+1} must have 'round' field")
            if i == 0:
                if "max_teams" not in round_data:
                    raise serializers.ValidationError("First round must have 'max_teams' field")
            else:
                if "qualifying_teams" not in round_data:
                    raise serializers.ValidationError(f"Round {i+1} must have 'qualifying_teams' field")

        return value

    def validate_placement_points(self, value):
        """Ensure placement_points is a valid JSON/dict"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for placement_points")

        if not isinstance(value, dict):
            raise serializers.ValidationError("placement_points must be an object/dictionary")

        return value

    def validate_prize_distribution(self, value):
        """Ensure prize_distribution is a valid JSON/dict"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for prize_distribution")

        if not isinstance(value, dict):
            raise serializers.ValidationError("prize_distribution must be an object/dictionary")

        return value

    def get_is_5v5(self, obj):
        """Check if tournament is a 5v5 game format (Valorant/COD)"""
        return obj.is_5v5_game()

    def get_requires_password(self, obj):
        """Check if tournament requires match passwords"""
        return obj.requires_password()

    def validate(self, attrs):
        """Root level validation for Tournament"""
        event_mode = attrs.get("event_mode", "TOURNAMENT")

        if event_mode == "SCRIM":
            # Additional Scrim validations
            max_matches = attrs.get("max_matches", 4)
            if max_matches > 4:
                raise serializers.ValidationError({"max_matches": "Scrims support a maximum of 4 matches."})

        return attrs

    def to_representation(self, instance):
        """Custom representation to ensure default banner fallback, tournament_file handling, and sponsors"""
        data = super().to_representation(instance)

        # Attach sponsors
        sponsors = instance.sponsors.all().order_by("display_order", "id")
        data["sponsors"] = TournamentSponsorSerializer(sponsors, many=True, context=self.context).data

        # Check if banner_image is null in the model instance
        if not instance.banner_image:
            default_banner_path = instance.get_default_banner_path()
            if settings.USE_S3:
                data["banner_image"] = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/{default_banner_path}"
            else:
                request = self.context.get("request")
                if request:
                    data["banner_image"] = request.build_absolute_uri(f"{settings.MEDIA_URL}{default_banner_path}")
                else:
                    data["banner_image"] = f"{settings.MEDIA_URL}{default_banner_path}"

        # Ensure tournament_file is null when not uploaded (no default fallback)
        if not instance.tournament_file:
            data["tournament_file"] = None

        return data


class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list views"""

    host_name = serializers.CharField(source="host.user.username", read_only=True)
    host = serializers.SerializerMethodField()
    banner_image = serializers.SerializerMethodField()

    is_featured = serializers.BooleanField(read_only=True)
    is_registered = serializers.SerializerMethodField()
    user_registration_status = serializers.SerializerMethodField()  # NEW: Return actual status for paid tournaments

    class Meta:
        model = Tournament
        fields = (
            "id",
            "title",
            "game_name",
            "game_mode",
            "host_name",
            "host",
            "max_participants",
            "current_participants",
            "entry_fee",
            "prize_pool",
            "registration_start",
            "registration_end",
            "tournament_start",
            "status",
            "banner_image",
            "is_featured",
            "is_registered",
            "user_registration_status",
            "plan_type",
            "homepage_banner",
            "event_mode",
            "updated_at",
            "rounds",
            "current_round",
            "round_names",
            "credential_release_time",
            "slot_list_release_time",
            "live_link",
        )

    def get_is_registered(self, obj):
        """Check if current user is CONFIRMED registered for this tournament (as captain or team member)"""
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False

        if not hasattr(request.user, "player_profile"):
            return False

        from tournaments.models import TournamentRegistration

        # Check if user is the captain with a confirmed registration
        if TournamentRegistration.objects.filter(
            tournament=obj,
            player=request.user.player_profile,
            status='confirmed'
        ).exists():
            return True

        # Check if user is a member of any confirmed team in this tournament
        return TournamentRegistration.objects.filter(
            tournament=obj,
            team__members__user=request.user,
            status='confirmed'
        ).exists()

    def get_user_registration_status(self, obj):
        """Return the actual registration status (pending_payment, confirmed, rejected, etc.) or check if registered via team invite"""
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None

        if not hasattr(request.user, "player_profile"):
            return None

        from tournaments.models import TournamentRegistration

        # Check if user is the captain (has direct TournamentRegistration)
        reg = TournamentRegistration.objects.filter(
            tournament=obj,
            player=request.user.player_profile
        ).first()

        if reg:
            return reg.status

        # Check if user is a team member of any team registered in this tournament
        is_team_member = TournamentRegistration.objects.filter(
            tournament=obj,
            team__members__user=request.user
        ).exclude(status='rejected').exists()

        if is_team_member:
            return 'confirmed'  # They're registered via accepted team invite

        return None

    def get_host(self, obj):
        return {"id": obj.host.id, "username": obj.host.user.username}

    def get_banner_image(self, obj):
        """Return custom banner for premium, default banner for basic/featured/premium fallback"""
        # If custom banner exists, return it
        if obj.banner_image:
            if settings.USE_S3:
                # S3 URL
                return obj.banner_image.url
            else:
                # Local URL
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(obj.banner_image.url)
                return obj.banner_image.url

        # Fallback to default banner for all plans
        default_banner_path = obj.get_default_banner_path()
        if settings.USE_S3:
            # Construct S3 URL for default banner
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/{default_banner_path}"
        else:
            # Local URL for default banner
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(f"{settings.MEDIA_URL}{default_banner_path}")
            return f"{settings.MEDIA_URL}{default_banner_path}"
