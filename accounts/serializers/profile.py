"""
Player and Host profile serializers.
"""
from django.core.cache import cache
from django.db.models import Avg, Q, Sum

from rest_framework import serializers

from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember
from accounts.serializers.user import UserSerializer
from accounts.tasks import update_host_rating_cache
from tournaments.models import HostRating, Tournament, TournamentRegistration


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
            "in_game_name",
            "game_id",
            "preferred_games",
            "notification_preferences",
            "game_profiles",
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
            "social_links",
            "notification_preferences",
            "payout_details",
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
