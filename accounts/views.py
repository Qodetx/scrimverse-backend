import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import models
from django.utils import timezone

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.google_auth import GoogleOAuth
from accounts.models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, User
from accounts.serializers import (
    HostProfileSerializer,
    HostRegistrationSerializer,
    LoginSerializer,
    PlayerProfileSerializer,
    PlayerRegistrationSerializer,
    TeamInviteDetailSerializer,
    TeamJoinRequestSerializer,
    TeamMemberSerializer,
    TeamSerializer,
    UserSerializer,
)
from accounts.tasks import process_team_invitation, send_verification_email_task, send_welcome_email_task
from accounts.validators import validate_aadhar_image
from tournaments.models import RoundScore, TournamentRegistration

logger = logging.getLogger(__name__)


class PlayerRegistrationView(generics.CreateAPIView):
    """
    Player Registration API
    POST /api/accounts/player/register/
    """

    serializer_class = PlayerRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")

        # Check if user already exists with this email
        if email:
            try:
                existing_user = User.objects.get(email=email)

                # If user exists but is NOT verified, delete the old account and allow re-registration
                if not existing_user.is_email_verified:
                    logger.info(
                        f"Deleting unverified account for {email} to allow re-registration (user_type: {existing_user.user_type})"  # noqa: E501
                    )
                    existing_user.delete()
                    # Continue with registration below
                else:
                    # User exists and is verified - return error
                    return Response(
                        {
                            "error": "An account with this email already exists and is verified. Please login instead.",
                            "email": email,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except User.DoesNotExist:
                # User doesn't exist, continue with registration
                pass

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        user.email_verification_token = verification_token
        user.email_verification_sent_at = timezone.now()
        user.is_email_verified = False  # Explicitly set to False
        user.is_active = False  # Deactivate account until email is verified
        user.save(
            update_fields=["email_verification_token", "email_verification_sent_at", "is_email_verified", "is_active"]
        )

        # Send verification email (NOT welcome email)
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        verification_url = f"{frontend_url}/verify-email/{verification_token}"

        send_verification_email_task.delay(
            user_email=user.email, user_name=user.username, verification_url=verification_url
        )
        logger.info(f"Verification email sent to player: {user.email}")

        # DO NOT return tokens - user must verify email first
        return Response(
            {
                "message": "Registration successful! Please check your email to verify your account.",
                "email": user.email,
                "verification_required": True,
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
        email = request.data.get("email")

        # Check if user already exists with this email
        if email:
            try:
                existing_user = User.objects.get(email=email)

                # If user exists but is NOT verified, delete the old account and allow re-registration
                if not existing_user.is_email_verified:
                    logger.info(
                        f"Deleting unverified account for {email} to allow re-registration (user_type: {existing_user.user_type})"  # noqa: E501
                    )
                    existing_user.delete()
                    # Continue with registration below
                else:
                    # User exists and is verified - return error
                    return Response(
                        {
                            "error": "An account with this email already exists and is verified. Please login instead.",
                            "email": email,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except User.DoesNotExist:
                # User doesn't exist, continue with registration
                pass

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        user.email_verification_token = verification_token
        user.email_verification_sent_at = timezone.now()
        user.is_email_verified = False  # Explicitly set to False
        user.is_active = False  # Deactivate account until email is verified
        user.save(
            update_fields=["email_verification_token", "email_verification_sent_at", "is_email_verified", "is_active"]
        )

        # Send verification email (NOT welcome email)
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        verification_url = f"{frontend_url}/verify-email/{verification_token}"

        send_verification_email_task.delay(
            user_email=user.email, user_name=user.username, verification_url=verification_url
        )
        logger.info(f"Verification email sent to host: {user.email}")

        # DO NOT return tokens - user must verify email first
        return Response(
            {
                "message": "Registration successful! Please check your email to verify your account.",
                "email": user.email,
                "verification_required": True,
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
        logger = logging.getLogger("accounts")

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user_type = serializer.validated_data["user_type"]

        logger.info(f"Login attempt - Email: {email}, User Type: {user_type}")

        # Check if user exists
        try:
            user_obj = User.objects.get(email=email)
            logger.debug(f"User found - ID: {user_obj.id}, Username: {user_obj.username}, Type: {user_obj.user_type}")
        except User.DoesNotExist:
            logger.warning(f"Login failed - No account found for email: {email}")
            return Response({"error": "No account found with this email address"}, status=status.HTTP_401_UNAUTHORIZED)

        # Authenticate user
        user = authenticate(request, username=email, password=password)

        if user is None:
            # Check if login failed because account is inactive
            if user_obj and not user_obj.is_active:
                logger.warning(f"Login failed - Account inactive/unverified for email: {email}")
                return Response(
                    {
                        "error": (
                            "Please verify your email address before logging in. "
                            "Check your inbox for the verification link."
                        )
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            logger.warning(f"Login failed - Incorrect password for email: {email}")
            return Response({"error": "Incorrect password. Please try again."}, status=status.HTTP_401_UNAUTHORIZED)

        # Check user type matches
        if user.user_type != user_type:
            logger.warning(
                f"Login failed - User type mismatch. Expected: {user_type}, Actual: {user.user_type} for email: {email}"
            )
            return Response(
                {"error": f"This account is not registered as a {user_type}"}, status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        logger.info(f"Login successful - User ID: {user.id}, Username: {user.username}, Type: {user.user_type}")

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


class GoogleAuthView(APIView):
    """
    Google OAuth Authentication for Player and Host
    POST /api/accounts/google-auth/

    Request body:
    {
        "token": "google_oauth_token",
        "user_type": "player" or "host"
    }
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get("token")
        user_type = request.data.get("user_type")
        username = request.data.get("username")  # Required for signup
        phone_number = request.data.get("phone_number")  # Required for signup
        is_signup = request.data.get("is_signup", False)  # Flag to distinguish login vs signup

        if not token:
            return Response({"error": "Google token is required"}, status=status.HTTP_400_BAD_REQUEST)

        if user_type not in ["player", "host"]:
            return Response({"error": "user_type must be 'player' or 'host'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Verify Google token and get user info
            google_user_info = GoogleOAuth.verify_google_token(token)

            if not google_user_info.get("email_verified"):
                return Response({"error": "Google email not verified"}, status=status.HTTP_400_BAD_REQUEST)

            email = google_user_info["email"]

            # Check if user already exists
            try:
                user = User.objects.get(email=email)

                # Check if user type matches
                if user.user_type != user_type:
                    return Response(
                        {"error": f"This email is already registered as a {user.user_type}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # User exists, log them in
                message = "Login successful!"

            except User.DoesNotExist:
                # User doesn't exist

                # If this is a login attempt (not signup), return error
                if not is_signup:
                    return Response(
                        {
                            "error": "account_not_found",
                            "message": "No account found with this email. Please sign up first.",
                            "redirect": "signup",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # This is a signup - validate required fields
                if not username or not phone_number:
                    return Response(
                        {"error": "Username and phone number are required for signup"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Validate username uniqueness
                if User.objects.filter(username=username).exists():
                    return Response(
                        {"error": "Username already taken. Please choose another."}, status=status.HTTP_400_BAD_REQUEST
                    )

                # Validate phone number
                if not phone_number.isdigit() or len(phone_number) != 10:
                    return Response(
                        {"error": "Phone number must be exactly 10 digits"}, status=status.HTTP_400_BAD_REQUEST
                    )

                # Create user without password (Google OAuth users)
                user = User.objects.create(
                    email=email,
                    username=username,
                    user_type=user_type,
                    phone_number=phone_number,
                    is_email_verified=True,  # Google already verified email
                    is_active=True,  # Activate account immediately
                )

                # Set unusable password for OAuth users
                user.set_unusable_password()
                user.save()

                # Create corresponding profile
                if user_type == "player":
                    PlayerProfile.objects.create(user=user)
                else:
                    HostProfile.objects.create(user=user)

                # Send welcome email asynchronously
                if user_type == "player":
                    dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/player/dashboard"
                else:
                    dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"

                send_welcome_email_task.delay(
                    user_email=user.email, user_name=user.username, dashboard_url=dashboard_url, user_type=user_type
                )
                logger.info(f"Welcome email queued for Google OAuth {user_type}: {user.email}")

                message = "Account created successfully!"
                logger.debug(f"Google OAuth account created - ID: {user.id}, Username: {username}, Type: {user_type}")

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # Get profile data
            if user_type == "player":
                profile = PlayerProfile.objects.get(user=user)
                profile_data = PlayerProfileSerializer(profile).data
            else:
                profile = HostProfile.objects.get(user=user)
                profile_data = HostProfileSerializer(profile).data

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "profile": profile_data,
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                    "message": message,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Authentication failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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


class CurrentUserView(APIView):
    """
    Get and Update current logged-in user details
    GET/PATCH /api/accounts/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user, context={"request": request})

        profile_data = None
        if user.user_type == "player" and hasattr(user, "player_profile"):
            profile_data = PlayerProfileSerializer(user.player_profile, context={"request": request}).data
        elif user.user_type == "host" and hasattr(user, "host_profile"):
            profile_data = HostProfileSerializer(user.host_profile, context={"request": request}).data

        return Response({"user": serializer.data, "profile": profile_data}, status=status.HTTP_200_OK)

    def patch(self, request):
        user = request.user
        data = request.data.copy()

        # Email cannot be changed
        if "email" in data:
            del data["email"]

        # Username change restriction logic
        new_username = data.get("username")
        if new_username and new_username != user.username:
            # If they have already changed it once
            if user.username_change_count > 0:
                # Check if 6 months (approx 180 days) have passed
                if user.last_username_change:
                    six_months_ago = timezone.now() - timedelta(days=180)
                    if user.last_username_change > six_months_ago:
                        days_left = (user.last_username_change + timedelta(days=180) - timezone.now()).days
                        return Response(
                            {
                                "error": (
                                    f"Username can only be changed once every 6 months. "
                                    f"Please try again in {days_left} days."
                                )
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            # Increment change count and update timestamp
            user.username_change_count += 1
            user.last_username_change = timezone.now()
            user.save()

        # Update user fields
        serializer = UserSerializer(user, data=data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


class IsPlayerUser(permissions.BasePermission):
    """
    Permission class to allow access only to player users
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "player"


class TeamViewSet(viewsets.ModelViewSet):
    """
    Team Management API
    """

    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """
        Allow unauthenticated access for list and retrieve actions
        """
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsPlayerUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        # For list action, check for "mine" parameter to filter by user's teams
        if self.action == "list":
            mine = self.request.query_params.get("mine") == "true"
            search = self.request.query_params.get("search", "").strip()

            if mine:
                queryset = Team.objects.filter(
                    models.Q(captain=self.request.user) | models.Q(members__user=self.request.user)
                ).distinct()
            else:
                queryset = Team.objects.all()

            # Apply search filter if provided
            if search:
                queryset = queryset.filter(name__icontains=search)

            return queryset

        # For actions that handle their own permission checks or should return 403 instead of 404
        # we return all teams and let the action/update/delete method handle the check.
        if self.action in [
            "retrieve",
            "update",
            "partial_update",
            "destroy",
            "leave_team",
            "request_join",
            "past_tournaments",
            "transfer_captaincy",
            "invite_player",
            "remove_member",
            "add_member",
            "accept_request",
            "reject_request",
            "appoint_captain",
            "join_requests",
        ]:
            return Team.objects.all()

        # Fallback
        return Team.objects.all()

    @action(detail=True, methods=["post"])
    def leave_team(self, request, pk=None):
        """Allow a player to leave a team"""
        team = self.get_object()

        # Check if user is a member
        member = TeamMember.objects.filter(team=team, user=request.user).first()
        if not member:
            return Response({"error": "You are not a member of this team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if captain
        if team.captain == request.user:
            # Captain is leaving - check if there are other members
            other_members = TeamMember.objects.filter(team=team).exclude(user=request.user).order_by("id")

            if other_members.exists():
                # Promote the oldest member (first added) to captain
                new_captain_member = other_members.first()

                if new_captain_member.user:
                    # Update team captain
                    team.captain = new_captain_member.user
                    team.save()

                    # Update captain flags
                    TeamMember.objects.filter(team=team).update(is_captain=False)
                    new_captain_member.is_captain = True
                    new_captain_member.save()

                    # Remove the old captain
                    member.delete()

                    logger.info(
                        f"Captain {request.user.username} left team {team.name}. "
                        f"New captain: {new_captain_member.username}"
                    )

                    return Response(
                        {
                            "message": f"You have left the team. {new_captain_member.username} is now the captain.",
                            "new_captain": new_captain_member.username,
                        },
                        status=status.HTTP_200_OK,
                    )
                else:
                    # Next member is not a registered user, cannot promote
                    return Response(
                        {
                            "error": "Cannot leave: next member is not a registered user. Please remove them first or delete the team."  # noqa: E501
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                # Captain is the only member - delete the team
                team_name = team.name
                team.delete()

                logger.info(f"Team {team_name} deleted as captain {request.user.username} was the only member")

                return Response(
                    {
                        "message": f"Team '{team_name}' has been deleted as you were the only member.",
                        "team_deleted": True,
                    },
                    status=status.HTTP_200_OK,
                )

        # Regular member leaving
        member.delete()
        logger.info(f"Member {request.user.username} left team {team.name}")
        return Response({"message": "Successfully left the team"}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        logger.debug(
            f"Create team request - Captain: {self.request.user.id}, Team name: {self.request.data.get('name')}"
        )

        # Check if user is already in a PERMANENT team (temporary teams are allowed)
        existing_membership = TeamMember.objects.filter(
            user=self.request.user, team__is_temporary=False  # Only check for permanent teams
        ).exists()
        if existing_membership:
            raise ValidationError({"error": "You are already a member of a team. Leave your current team first."})

        player_usernames = self.request.data.get("player_usernames", [])

        # ✅ VALIDATE: All player_usernames must be registered players
        if player_usernames:
            invalid_usernames = []
            for username in player_usernames:
                if username and username != self.request.user.username:
                    user_exists = User.objects.filter(username=username, user_type="player").exists()
                    if not user_exists:
                        invalid_usernames.append(username)

            if invalid_usernames:
                raise ValidationError(
                    {
                        "error": f"The following players were not found: {', '.join(invalid_usernames)}. Only registered ScrimVerse players can be added to teams."  # noqa: E501
                    }
                )

        team = serializer.save(captain=self.request.user)
        logger.debug(f"Team created - ID: {team.id}, Name: {team.name}, Captain: {self.request.user.username}")

        # Add captain as the first member
        TeamMember.objects.create(
            team=team, user=self.request.user, username=self.request.user.username, is_captain=True
        )

        # Add additional members from player_usernames (all validated now)
        for username in player_usernames:
            if username and username != self.request.user.username:
                user_obj = User.objects.get(username=username, user_type="player")  # Use .get() since we validated
                TeamMember.objects.create(team=team, username=username, user=user_obj, is_captain=False)

    def update(self, request, *args, **kwargs):
        """Update team details (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can edit team details"}, status=status.HTTP_403_FORBIDDEN)

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(team, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """Partial update team details (captain only)"""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        team = self.get_object()

        logger.debug(
            f"Add member request - Team: {team.id}, Captain: {request.user.id}, New member: {request.data.get('username')}"  # noqa E501
        )

        if team.captain != request.user:
            return Response({"error": "Only the captain can add members"}, status=status.HTTP_403_FORBIDDEN)

        if team.members.count() >= 15:
            return Response({"error": "Team cannot have more than 15 members"}, status=status.HTTP_400_BAD_REQUEST)

        username = request.data.get("username")
        if not username:
            return Response({"error": "Username is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ VALIDATE: User must exist and be a player
        user = User.objects.filter(username=username, user_type="player").first()
        if not user:
            return Response(
                {"error": f"Player '{username}' not found. Only registered ScrimVerse players can be added to teams."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already a member
        if TeamMember.objects.filter(team=team, username=username).exists():
            return Response({"error": "Member already exists"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user is already in another PERMANENT team
        if TeamMember.objects.filter(user=user, team__is_temporary=False).exclude(team=team).exists():
            return Response(
                {"error": f"{username} is already a member of another team"}, status=status.HTTP_400_BAD_REQUEST
            )

        member = TeamMember.objects.create(team=team, username=username, user=user, is_captain=False)

        logger.debug(f"Member added - Team: {team.id}, Member: {username}, User ID: {user.id}")

        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only the captain can remove members"}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not member:
            return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        if member.user == team.captain:
            return Response(
                {"error": "Cannot remove the captain. Transfer captaincy first."}, status=status.HTTP_400_BAD_REQUEST
            )

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def transfer_captaincy(self, request, pk=None):
        team = self.get_object()
        if team.captain != request.user:
            return Response(
                {"error": "Only the current captain can transfer captaincy"}, status=status.HTTP_403_FORBIDDEN
            )

        member_id = request.data.get("member_id")
        new_captain_member = TeamMember.objects.filter(team=team, id=member_id).first()

        if not new_captain_member or not new_captain_member.user:
            return Response(
                {"error": "New captain must be a registered user in the team"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Update team captain
        team.captain = new_captain_member.user
        team.save()

        # Update flags
        TeamMember.objects.filter(team=team).update(is_captain=False)
        new_captain_member.is_captain = True
        new_captain_member.save()

        return Response(TeamSerializer(team).data)

    @action(detail=True, methods=["post"])
    def request_join(self, request, pk=None):
        """Player requests to join a team"""
        team = self.get_object()

        logger.debug(f"Join request - Team: {team.id}, Player: {request.user.id}")

        # Check if user is already in a PERMANENT team
        if TeamMember.objects.filter(user=request.user, team__is_temporary=False).exists():
            return Response({"error": "You are already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if team is full
        if team.members.count() >= 15:
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update join request
        join_request, created = TeamJoinRequest.objects.get_or_create(
            team=team, player=request.user, defaults={"status": "pending", "request_type": "request"}
        )

        if not created:
            if join_request.status == "rejected":
                join_request.status = "pending"
                join_request.request_type = "request"
                join_request.save()
            elif join_request.request_type == "invite" and join_request.status == "pending":
                return Response(
                    {"message": "You already have a pending invite from this team"}, status=status.HTTP_400_BAD_REQUEST
                )

        logger.debug(
            f"Join request created - Team: {team.id}, Player: {request.user.username}, Status: {join_request.status}"
        )

        return Response({"message": "Join request sent"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def invite_player(self, request, pk=None):
        """Captain invites a player to the team"""
        team = self.get_object()

        logger.debug(
            f"Invite player request - Team: {team.id}, Captain: {request.user.id}, Player ID: {request.data.get('player_id')}"  # noqa E501
        )

        if team.captain != request.user:
            return Response({"error": "Only captains can invite players"}, status=status.HTTP_403_FORBIDDEN)

        player_id = request.data.get("player_id")
        if not player_id:
            return Response({"error": "player_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            player = User.objects.get(id=player_id, user_type="player")
        except User.DoesNotExist:
            return Response({"error": "Player not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if player is already in a PERMANENT team
        if TeamMember.objects.filter(user=player, team__is_temporary=False).exists():
            return Response({"error": "Player is already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if team is full
        if team.members.count() >= 15:
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        # Create or update invite
        invite, created = TeamJoinRequest.objects.get_or_create(
            team=team, player=player, defaults={"status": "pending", "request_type": "invite"}
        )

        if not created:
            if invite.status == "rejected":
                invite.status = "pending"
                invite.request_type = "invite"
                invite.save()
            elif invite.request_type == "request" and invite.status == "pending":
                # Automatically accept if player already requested to join
                TeamMember.objects.create(team=team, user=player, username=player.username, is_captain=False)
                invite.status = "accepted"
                invite.save()
                return Response(
                    {"message": "Player already had a join request. They have been added to the team."},
                    status=status.HTTP_200_OK,
                )

        # Process invitation async (email notifications disabled for now)
        process_team_invitation.delay(team.id, player.id, "invite")

        return Response({"message": "Invitation sent"}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def my_invites(self, request):
        """Get pending invitations for the current user"""
        invites = TeamJoinRequest.objects.filter(player=request.user, status="pending", request_type="invite")
        serializer = TeamJoinRequestSerializer(invites, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def handle_invite(self, request):
        """Accept or reject an invitation"""
        invite_id = request.data.get("invite_id")
        action = request.data.get("action")  # 'accept' or 'reject'

        if not invite_id or action not in ["accept", "reject"]:
            return Response({"error": "invite_id and valid action are required"}, status=status.HTTP_400_BAD_REQUEST)

        invite = TeamJoinRequest.objects.filter(
            id=invite_id, player=request.user, status="pending", request_type="invite"
        ).first()
        if not invite:
            return Response({"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND)

        if action == "accept":
            team = invite.team
            # Check if player is already in a team
            if TeamMember.objects.filter(user=request.user, team__is_temporary=False).exists():
                return Response({"error": "You are already a member of a team"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if team is full
            if team.members.count() >= 15:
                return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

            # Add member
            TeamMember.objects.create(team=team, user=request.user, username=request.user.username, is_captain=False)
            invite.status = "accepted"
            invite.save()

            return Response({"message": "Invitation accepted"}, status=status.HTTP_200_OK)
        else:
            invite.status = "rejected"
            invite.save()

            return Response({"message": "Invitation rejected"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def join_requests(self, request, pk=None):
        """Get pending join requests for a team (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only captains can view join requests"}, status=status.HTTP_403_FORBIDDEN)

        requests = team.join_requests.filter(status="pending", request_type="request")
        serializer = TeamJoinRequestSerializer(requests, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def accept_request(self, request, pk=None):
        """Accept a join request (captain only)"""
        logger = logging.getLogger("accounts")
        team = self.get_object()

        logger.info(
            f"Accept request attempt - Team: {team.id} ({team.name}), Captain: {request.user.id} ({request.user.username})"  # noqa E501
        )

        if team.captain != request.user:
            logger.warning(f"Unauthorized accept attempt - User {request.user.id} is not captain of team {team.id}")
            return Response({"error": "Only captains can accept requests"}, status=status.HTTP_403_FORBIDDEN)

        request_id = request.data.get("request_id")
        logger.debug(f"Processing join request ID: {request_id} for team {team.id}")

        join_request = team.join_requests.filter(id=request_id, status="pending").first()

        if not join_request:
            logger.error(f"Join request {request_id} not found or not pending for team {team.id}")
            return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Found join request - Player: {join_request.player.id} ({join_request.player.username})")

        # Check if team is full
        current_member_count = team.members.count()
        if current_member_count >= 15:
            logger.warning(f"Team {team.id} is full ({current_member_count}/15 members)")
            return Response({"error": "Team is full"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Add member
            new_member = TeamMember.objects.create(
                team=team, user=join_request.player, username=join_request.player.username, is_captain=False
            )
            logger.info(
                f"Created team member - Member ID: {new_member.id}, User: {join_request.player.username}, Team: {team.name}"  # noqa E501
            )

            join_request.status = "accepted"
            join_request.save()
            logger.info(f"Join request {request_id} accepted successfully")

            return Response({"message": "Request accepted"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error accepting join request {request_id}: {str(e)}", exc_info=True)
            return Response({"error": "Failed to accept request"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def reject_request(self, request, pk=None):
        """Reject a join request (captain only)"""
        logger = logging.getLogger("accounts")
        team = self.get_object()

        logger.info(
            f"Reject request attempt - Team: {team.id} ({team.name}), Captain: {request.user.id} ({request.user.username})"  # noqa E501
        )

        if team.captain != request.user:
            logger.warning(f"Unauthorized reject attempt - User {request.user.id} is not captain of team {team.id}")
            return Response({"error": "Only captains can reject requests"}, status=status.HTTP_403_FORBIDDEN)

        request_id = request.data.get("request_id")
        logger.debug(f"Processing rejection for join request ID: {request_id}")

        join_request = team.join_requests.filter(id=request_id, status="pending").first()

        if not join_request:
            logger.error(f"Join request {request_id} not found or not pending for team {team.id}")
            return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Rejecting join request from player: {join_request.player.id} ({join_request.player.username})")

        join_request.status = "rejected"
        join_request.save()

        logger.info(f"Join request {request_id} rejected successfully")

        return Response({"message": "Request rejected"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def appoint_captain(self, request, pk=None):
        """Appoint a new captain (captain only)"""
        team = self.get_object()
        if team.captain != request.user:
            return Response({"error": "Only captains can appoint new captains"}, status=status.HTTP_403_FORBIDDEN)

        member_id = request.data.get("member_id")
        member = team.members.filter(id=member_id).first()

        if not member or not member.user:
            return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)

        # Update team captain
        team.captain = member.user
        team.save()

        # Update member roles
        team.members.update(is_captain=False)
        member.is_captain = True
        member.save()

        return Response({"message": "Captain appointed"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def past_tournaments(self, request, pk=None):
        """Get past tournaments for a team"""
        team = self.get_object()

        # Get all completed tournaments this team participated in
        registrations = (
            TournamentRegistration.objects.filter(team=team, tournament__status="completed", status="confirmed")
            .select_related("tournament")
            .order_by("-tournament__tournament_end")
        )

        tournaments_data = []
        for reg in registrations:
            tournament = reg.tournament

            # Determine placement
            placement = "Participated"

            # Check if this team won (check winners JSON field)
            if tournament.winners:
                # Winners is a dict like {'1': reg_id, '2': reg_id} for each round
                # The final round winner is the tournament winner
                final_round = str(tournament.get_total_rounds())
                if final_round in tournament.winners and tournament.winners[final_round] == reg.id:
                    placement = "1st Place - Winner"

            # Try to get placement from round scores if available
            if placement == "Participated":
                try:
                    # Get total points across all rounds
                    total_score = (
                        RoundScore.objects.filter(tournament=tournament, team=reg).aggregate(
                            total=models.Sum("total_points")
                        )["total"]
                        or 0
                    )

                    if total_score > 0:
                        # Get all teams' total scores for this tournament
                        all_scores = (
                            RoundScore.objects.filter(tournament=tournament)
                            .values("team")
                            .annotate(total=models.Sum("total_points"))
                            .order_by("-total")
                        )

                        # Find this team's position
                        position = 1
                        for score in all_scores:
                            if score["team"] == reg.id:
                                if position == 1:
                                    placement = "1st Place"
                                elif position == 2:
                                    placement = "2nd Place"
                                elif position == 3:
                                    placement = "3rd Place"
                                else:
                                    placement = f"{position}th Place"
                                break
                            position += 1
                except Exception as e:
                    print(f"Error calculating placement: {e}")
                    placement = "Participated"

            # Format date
            date_str = (
                tournament.tournament_end.strftime("%m/%d/%Y")
                if tournament.tournament_end
                else tournament.tournament_start.strftime("%m/%d/%Y")
                if tournament.tournament_start
                else "N/A"
            )

            tournaments_data.append(
                {
                    "id": tournament.id,
                    "name": tournament.title,
                    "date": date_str,
                    "placement": placement,
                    "status": "completed",
                    "tournament_type": tournament.event_mode.lower() if tournament.event_mode else "tournament",
                }
            )

        return Response(tournaments_data, status=status.HTTP_200_OK)

# ============================================================================
# TEAM INVITE ENDPOINTS (Invite-Based Registration Flow)
# ============================================================================


class RetrieveInviteDetailsView(APIView):
    """
    Retrieve invite details before accepting/declining.
    GET /api/accounts/invites/<token>/
    
    Permission: AllowAny (guests can view invite details)
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        """
        Retrieve invite details by token.
        Returns safe public data about the team and tournament.
        """
        try:
            invite = TeamJoinRequest.objects.select_related(
                "team", "tournament_registration__tournament", "tournament_registration__player__user"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if expired
        if invite.invite_expires_at and timezone.now() > invite.invite_expires_at:
            invite.status = "expired"
            invite.save(update_fields=["status"])
            return Response(
                {"error": "This invite has expired", "status": "expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return safe public data
        registration = invite.tournament_registration
        tournament = registration.tournament if registration else None

        response_data = {
            "team_name": invite.team.name,
            "captain_name": registration.player.user.username if registration else "Unknown",
            "tournament_name": tournament.title if tournament else "Unknown",
            "status": invite.status,
            "invited_email": invite.invited_email,
            "invite_expires_at": invite.invite_expires_at,
        }

        serializer = TeamInviteDetailSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AcceptInviteView(APIView):
    """
    Accept invite and join the team.
    POST /api/accounts/invites/<token>/accept/
    
    Permission: IsAuthenticated (user must be logged in)
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, token):
        """
        Accept invite, add user to team, and update registration status.
        """
        user = request.user

        try:
            invite = TeamJoinRequest.objects.select_related(
                "team", "tournament_registration__tournament"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if expired
        if invite.invite_expires_at and timezone.now() > invite.invite_expires_at:
            invite.status = "expired"
            invite.save(update_fields=["status"])
            return Response(
                {"error": "This invite has expired", "status": "expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate email matches
        if user.email.lower() != invite.invited_email.lower():
            logger.warning(
                f"Email mismatch for invite {token}: user={user.email}, invited={invite.invited_email}"
            )
            return Response(
                {
                    "error": "Your email does not match the invited email. Please log in with the correct account.",
                    "invited_email": invite.invited_email,
                    "your_email": user.email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ================================================================
        # ACCEPT LOGIC (within atomic transaction)
        # ================================================================
        from django.db import transaction

        with transaction.atomic():
            # 1. Update TeamJoinRequest
            invite.status = "accepted"
            invite.player = user
            invite.save(update_fields=["status", "player", "updated_at"])

            logger.info(f"Invite {token} accepted by user {user.username}")

            # 2. Add user to team (create/update TeamMember)
            team = invite.team
            team_member, created = TeamMember.objects.get_or_create(
                team=team,
                username=user.username,
                defaults={
                    "user": user,
                    "is_captain": False,
                },
            )
            if not created and not team_member.user:
                # Update the link if we're filling it in for the first time
                team_member.user = user
                team_member.save(update_fields=["user"])

            logger.info(f"User {user.username} added to team {team.name}")

            # 3. Update TournamentRegistration.invited_members_status
            registration = invite.tournament_registration
            if registration:
                if not registration.invited_members_status:
                    registration.invited_members_status = {}

                # Find the entry matching this email and update it
                for email_key, member_status in registration.invited_members_status.items():
                    if email_key.lower() == invite.invited_email.lower():
                        member_status["status"] = "accepted"
                        member_status["username"] = user.username
                        break

                registration.save(update_fields=["invited_members_status", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {invite.invited_email} accepted by {user.username}"
                )

        return Response(
            {
                "success": True,
                "message": f"Successfully accepted invite and joined {team.name}!",
                "team_id": team.id,
                "team_name": team.name,
            },
            status=status.HTTP_200_OK,
        )


class DeclineInviteView(APIView):
    """
    Decline invite without joining the team.
    POST /api/accounts/invites/<token>/decline/
    
    Permission: AllowAny (allow declining without login)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        """
        Decline invite and mark as rejected.
        """
        try:
            invite = TeamJoinRequest.objects.select_related(
                "tournament_registration__tournament"
            ).get(invite_token=token, request_type="invite")
        except TeamJoinRequest.DoesNotExist:
            return Response(
                {"error": "Invite not found or invalid token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ================================================================
        # DECLINE LOGIC
        # ================================================================
        from django.db import transaction

        with transaction.atomic():
            # 1. Update TeamJoinRequest status
            invite.status = "rejected"
            invite.save(update_fields=["status", "updated_at"])

            logger.info(f"Invite {token} declined")

            # 2. Update TournamentRegistration.invited_members_status
            registration = invite.tournament_registration
            if registration:
                if not registration.invited_members_status:
                    registration.invited_members_status = {}

                # Find the entry matching this email and update it
                for email_key, member_status in registration.invited_members_status.items():
                    if email_key.lower() == invite.invited_email.lower():
                        member_status["status"] = "declined"
                        # username stays None since they declined
                        break

                registration.save(update_fields=["invited_members_status", "updated_at"])
                logger.info(
                    f"Registration {registration.id} updated: {invite.invited_email} declined invite"
                )

        return Response(
            {
                "success": True,
                "message": "Invite declined successfully",
                "invited_email": invite.invited_email,
            },
            status=status.HTTP_200_OK,
        )