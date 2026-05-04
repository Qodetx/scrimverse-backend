import logging

from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from tournaments.models import Tournament, TournamentSponsor
from tournaments.serializers import TournamentSponsorSerializer
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger(__name__)


class TournamentSponsorListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/tournaments/<tournament_id>/sponsors/  — public list
    POST /api/tournaments/<tournament_id>/sponsors/  — host only, add sponsor
    """

    serializer_class = TournamentSponsorSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [IsHostUser()]

    def get_queryset(self):
        return TournamentSponsor.objects.filter(tournament_id=self.kwargs["tournament_id"])

    def perform_create(self, serializer):
        tournament = get_object_or_404(Tournament, pk=self.kwargs["tournament_id"])
        # Only the tournament's host can add sponsors
        if tournament.host.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not own this tournament.")
        # Auto-assign display_order as next in sequence
        last_order = TournamentSponsor.objects.filter(tournament=tournament).order_by("-display_order").values_list("display_order", flat=True).first()
        next_order = (last_order or 0) + 1
        serializer.save(tournament=tournament, display_order=next_order)


class TournamentSponsorDetailView(APIView):
    """
    PATCH /api/tournaments/<tournament_id>/sponsors/<sponsor_id>/  — update order
    DELETE /api/tournaments/<tournament_id>/sponsors/<sponsor_id>/ — remove
    """

    permission_classes = [IsHostUser]
    parser_classes = [MultiPartParser, FormParser]

    def _get_sponsor(self, tournament_id, sponsor_id, user):
        tournament = get_object_or_404(Tournament, pk=tournament_id)
        if tournament.host.user != user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not own this tournament.")
        return get_object_or_404(TournamentSponsor, pk=sponsor_id, tournament=tournament)

    def patch(self, request, tournament_id, sponsor_id):
        sponsor = self._get_sponsor(tournament_id, sponsor_id, request.user)
        serializer = TournamentSponsorSerializer(sponsor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, tournament_id, sponsor_id):
        sponsor = self._get_sponsor(tournament_id, sponsor_id, request.user)
        sponsor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
