from django.contrib.auth import authenticate

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import HostProfile, PlayerProfile
from .serializers import (
    HostProfileSerializer,
    HostRegistrationSerializer,
    LoginSerializer,
    PlayerProfileSerializer,
    PlayerRegistrationSerializer,
    UserSerializer,
)


class PlayerRegistrationView(generics.CreateAPIView):
    """
    Player Registration API
    POST /api/accounts/player/register/
    """

    serializer_class = PlayerRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "message": "Player registered successfully!",
            },
            status=status.HTTP_201_CREATED,
        )


class HostRegistrationView(generics.CreateAPIView):
    """
    Host Registration API
    POST /api/accounts/host/register/
    """

    serializer_class = HostRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "message": "Host registered successfully!",
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    Login API for both Players and Hosts
    POST /api/accounts/login/
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user_type = serializer.validated_data["user_type"]

        # Authenticate user
        user = authenticate(request, username=email, password=password)

        if user is None:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # Check user type matches
        if user.user_type != user_type:
            return Response(
                {"error": f"This account is not registered as a {user_type}"}, status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "message": "Login successful!",
            },
            status=status.HTTP_200_OK,
        )


class PlayerProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Player Profile
    GET/PUT /api/accounts/player/profile/<id>/
    """

    queryset = PlayerProfile.objects.all()
    serializer_class = PlayerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]


class HostProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Host Profile
    GET/PUT /api/accounts/host/profile/<id>/
    """

    queryset = HostProfile.objects.all()
    serializer_class = HostProfileSerializer
    permission_classes = [permissions.IsAuthenticated]


class CurrentUserView(APIView):
    """
    Get current logged-in user details
    GET /api/accounts/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)

        profile_data = None
        if user.user_type == "player" and hasattr(user, "player_profile"):
            profile_data = PlayerProfileSerializer(user.player_profile).data
        elif user.user_type == "host" and hasattr(user, "host_profile"):
            profile_data = HostProfileSerializer(user.host_profile).data

        return Response({"user": serializer.data, "profile": profile_data}, status=status.HTTP_200_OK)
