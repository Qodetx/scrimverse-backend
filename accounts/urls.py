from django.urls import include, path

from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.email_verification_views import (
    PublicResendVerificationEmailView,
    SendVerificationEmailView,
    VerifyEmailView,
)
from accounts.leaderboard_views import LeaderboardView, TeamRankView
from accounts.views import (
    CurrentHostProfileView,
    CurrentPlayerProfileView,
    CurrentUserView,
    GoogleAuthView,
    HostProfileView,
    HostRegistrationView,
    HostSearchView,
    LoginView,
    PlayerProfileView,
    PlayerRegistrationView,
    PlayerUsernameSearchView,
    TeamViewSet,
    UploadAadharView,
    UserDetailView,
)

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")

urlpatterns = [
    # Authentication
    path("player/register/", PlayerRegistrationView.as_view(), name="player-register"),
    path("host/register/", HostRegistrationView.as_view(), name="host-register"),
    path("login/", LoginView.as_view(), name="login"),
    path("google-auth/", GoogleAuthView.as_view(), name="google-auth"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Email Verification
    path("send-verification-email/", SendVerificationEmailView.as_view(), name="send-verification-email"),
    path("verify-email/<str:token>/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", PublicResendVerificationEmailView.as_view(), name="resend-verification"),
    # Profile Management (must be before router to avoid conflicts)
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("player/profile/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("player/profile/me/", CurrentPlayerProfileView.as_view(), name="current-player-profile"),
    path("host/profile/<int:pk>/", HostProfileView.as_view(), name="host-profile"),
    path("host/profile/me/", CurrentHostProfileView.as_view(), name="current-host-profile"),
    path("host/upload-aadhar/", UploadAadharView.as_view(), name="upload-aadhar"),
    # Search
    path("players/search/", PlayerUsernameSearchView.as_view(), name="player-username-search"),
    path("hosts/search/", HostSearchView.as_view(), name="host-search"),
    # Leaderboard
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("teams/<int:team_id>/rank/", TeamRankView.as_view(), name="team-rank"),
    # Router URLs (must be last)
    path("", include(router.urls)),
]
