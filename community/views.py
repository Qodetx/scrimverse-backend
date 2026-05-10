from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CommunityJoin, CommunitySettings

VALID_COMMUNITY_TYPES = {CommunityJoin.WHATSAPP, CommunityJoin.INSTAGRAM}


class CommunitySettingsView(APIView):
    """
    GET /api/community/settings/
    Public — returns WhatsApp and Instagram links set by admin.
    Frontend uses this to decide whether to show community buttons.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        settings = CommunitySettings.load()
        return Response({
            "whatsapp_link": settings.whatsapp_link,
            "instagram_link": settings.instagram_link,
        })


class CommunityJoinView(APIView):
    """
    POST /api/community/join/
    Auth required — records that the user clicked a community join button.
    Idempotent: calling it multiple times for the same community_type is a no-op.
    Body: { "community_type": "whatsapp" | "instagram" }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        community_type = request.data.get("community_type", "").lower()
        if community_type not in VALID_COMMUNITY_TYPES:
            return Response(
                {"error": f"Invalid community_type. Must be one of: {', '.join(VALID_COMMUNITY_TYPES)}"},
                status=400,
            )
        CommunityJoin.objects.get_or_create(
            user=request.user,
            community_type=community_type,
        )
        return Response({"status": "ok", "community_type": community_type})


class CommunityStatusView(APIView):
    """
    GET /api/community/status/
    Auth required — returns whether the current user has joined each community.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        joined_types = set(
            CommunityJoin.objects.filter(user=request.user).values_list(
                "community_type", flat=True
            )
        )
        return Response({
            "whatsapp_joined": CommunityJoin.WHATSAPP in joined_types,
            "instagram_joined": CommunityJoin.INSTAGRAM in joined_types,
        })
