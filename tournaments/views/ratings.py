import logging

from rest_framework import generics, permissions

from accounts.models import HostProfile, PlayerProfile
from accounts.tasks import update_host_rating_cache
from tournaments.models import HostRating
from tournaments.serializers import HostRatingSerializer
from tournaments.views.permissions import IsPlayerUser

logger = logging.getLogger(__name__)


class HostRatingCreateView(generics.CreateAPIView):
    """
    Player rates a host
    POST /api/tournaments/host/<host_id>/rate/
    """

    serializer_class = HostRatingSerializer
    permission_classes = [IsPlayerUser]

    def perform_create(self, serializer):
        player_profile = PlayerProfile.objects.get(user=self.request.user)
        host_id = self.kwargs["host_id"]
        host_profile = HostProfile.objects.get(id=host_id)

        serializer.save(player=player_profile, host=host_profile)
        update_host_rating_cache.delay(host_profile.id)


class HostRatingsListView(generics.ListAPIView):
    """
    Get all ratings for a host
    GET /api/tournaments/host/<host_id>/ratings/
    """

    serializer_class = HostRatingSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        host_id = self.kwargs["host_id"]
        return HostRating.objects.filter(host_id=host_id)
