import logging

from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, TeamMember, User
from accounts.serializers import (
    HostProfileSerializer,
    PlayerProfileSerializer,
    UserSerializer,
)
from accounts.validators import validate_aadhar_image

logger = logging.getLogger(__name__)


class PlayerProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Player Profile
    GET/PUT /api/accounts/player/profile/<id>/
    """

    queryset = PlayerProfile.objects.all()
    serializer_class = PlayerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]


class CurrentPlayerProfileView(APIView):
    """
    Update current player's profile
    PATCH /api/accounts/player/profile/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        user = request.user
        if user.user_type != "player":
            return Response({"error": "Only players can update player profiles"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "player_profile"):
            return Response({"error": "Player profile not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PlayerProfileSerializer(user.player_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.debug(f"Player profile updated - User: {user.id}, Username: {user.username}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HostProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Host Profile
    GET/PUT /api/accounts/host/profile/<id>/
    """

    queryset = HostProfile.objects.all()
    serializer_class = HostProfileSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


class CurrentHostProfileView(APIView):
    """
    Update current host's profile
    PATCH /api/accounts/host/profile/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        user = request.user
        if user.user_type != "host":
            return Response({"error": "Only hosts can update host profiles"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "host_profile"):
            return Response({"error": "Host profile not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = HostProfileSerializer(user.host_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.debug(f"Host profile updated - User: {user.id}, Username: {user.username}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UploadAadharView(APIView):
    """
    Upload Aadhar card for host verification
    POST /api/accounts/host/upload-aadhar/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.user_type != "host":
            return Response({"error": "Only hosts can upload Aadhar cards"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "host_profile"):
            return Response({"error": "Host profile not found"}, status=status.HTTP_404_NOT_FOUND)

        host_profile = user.host_profile

        # Get uploaded files
        aadhar_front = request.FILES.get("aadhar_card_front")
        aadhar_back = request.FILES.get("aadhar_card_back")

        if not aadhar_front or not aadhar_back:
            return Response(
                {"error": "Both front and back images of Aadhar card are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate files using the model's validators
        try:
            validate_aadhar_image(aadhar_front)
            validate_aadhar_image(aadhar_back)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Update host profile
        host_profile.aadhar_card_front = aadhar_front
        host_profile.aadhar_card_back = aadhar_back
        host_profile.aadhar_uploaded_at = timezone.now()
        host_profile.verification_status = "pending"
        host_profile.save()

        return Response(
            {
                "message": "Aadhar card uploaded successfully. Your verification is pending admin approval.",
                "verification_status": host_profile.verification_status,
                "aadhar_uploaded_at": host_profile.aadhar_uploaded_at,
            },
            status=status.HTTP_200_OK,
        )


class UserDetailView(APIView):
    """
    Get any user's public profile by ID
    GET /api/accounts/users/{id}/
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to view profiles

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user)

        profile_data = None
        if user.user_type == "player" and hasattr(user, "player_profile"):
            profile_data = PlayerProfileSerializer(user.player_profile).data
        elif user.user_type == "host" and hasattr(user, "host_profile"):
            profile_data = HostProfileSerializer(user.host_profile).data

        return Response({"user": serializer.data, "profile": profile_data}, status=status.HTTP_200_OK)


class PlayerUsernameSearchView(APIView):
    """
    Search for players by username (for team registration autocomplete)
    GET /api/accounts/players/search/?q=<username>
    Returns list of matching player usernames and details
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to search

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        for_team = request.query_params.get("for_team", "false").lower() == "true"

        if not query or len(query) < 2:
            return Response({"results": []}, status=status.HTTP_200_OK)

        # Base query - search for players by username
        players = PlayerProfile.objects.filter(
            user__username__icontains=query, user__user_type="player"
        ).select_related("user")

        # If searching for team creation, apply additional filters
        if for_team:
            # Get all user IDs who are already in PERMANENT teams
            users_in_teams = TeamMember.objects.filter(team__is_temporary=False).values_list("user_id", flat=True)

            # EXCLUDE players who are already in permanent teams
            players = players.exclude(user_id__in=users_in_teams)

            # Exclude current user if authenticated (they're already the captain)
            if request.user.is_authenticated:
                players = players.exclude(user=request.user)

        # Apply slice AFTER all filters
        players = players[:10]

        results = [
            {
                "id": player.user.id,
                "username": player.user.username,
                "email": player.user.email,
                "profile_picture": player.user.profile_picture.url if player.user.profile_picture else None,
                "in_team": TeamMember.objects.filter(user=player.user, team__is_temporary=False).exists()
                if not for_team
                else False,
            }
            for player in players
        ]

        # Handle absolute URLs if request is available
        for res in results:
            if res["profile_picture"] and not res["profile_picture"].startswith("http"):
                res["profile_picture"] = request.build_absolute_uri(res["profile_picture"])

        logger.debug(f"Player search results - Query: {query}, For Team: {for_team}, Results: {len(results)}")
        return Response({"results": results}, status=status.HTTP_200_OK)


class HostSearchView(APIView):
    """
    Search for hosts by username or organization name
    GET /api/accounts/hosts/search/?q=<query>
    Returns list of matching hosts and details
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to search

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if not query or len(query) < 2:
            return Response({"results": []}, status=status.HTTP_200_OK)

        # Search for hosts by username
        hosts = HostProfile.objects.filter(user__username__icontains=query, user__user_type="host").select_related(
            "user"
        )[
            :10
        ]  # Limit to 10 results

        results = [
            {
                "id": host.id,  # Return host profile ID
                "username": host.user.username,
                "email": host.user.email,
                "verified": host.verified,
                "profile_picture": host.user.profile_picture.url if host.user.profile_picture else None,
            }
            for host in hosts
        ]

        # Handle absolute URLs if request is available
        for res in results:
            if res["profile_picture"] and not res["profile_picture"].startswith("http"):
                res["profile_picture"] = request.build_absolute_uri(res["profile_picture"])

        logger.debug(f"Host search results - Query: {query}, Results: {len(results)}")
        return Response({"results": results}, status=status.HTTP_200_OK)
