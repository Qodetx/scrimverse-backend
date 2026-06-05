from django.urls import include, path

from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.email_verification_views import (
    PublicResendVerificationEmailView,
    SendVerificationEmailView,
    VerifyEmailView,
)
from accounts.analytics_views import (
    PlayerAnalyticsActivityView,
    PlayerAnalyticsRecentResultsView,
    PlayerAnalyticsStatsView,
    PlayerAnalyticsTrendView,
    PlayerAnalyticsWeeklyActivityView,
    PlayerAnalyticsWeeklyTrendView,
    PlayerTeamAnalyticsView,
)
from accounts.leaderboard_views import LeaderboardView, TeamRankView
from accounts.notification_views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    NotificationDeleteView,
    NotificationBulkActionView,
)
from accounts.contact_views import ContactFormView, ReportIssueView
from accounts.password_reset_views import RequestPasswordResetView, ResetPasswordView, VerifyResetTokenView
from accounts.views import (
    ChangePasswordView,
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
    RetrieveInviteDetailsView,
    AcceptInviteView,
    DeclineInviteView,
    SendOTPView,
    UpdatePhoneView,
    UpdatePhoneMsg91View,
    SendRegistrationOTPView,
    VerifyRegistrationOTPView,
    ExportDataView,
    DeleteAccountView,
    RequestDataExportView,
    DataExportDetailView,
    DataExportPDFView,
    SendPhoneAuthOTPView,
    PhoneLoginView,
    PhoneRegisterView,
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
    # Password Reset
    path("request-password-reset/", RequestPasswordResetView.as_view(), name="request-password-reset"),
    path("verify-reset-token/<str:token>/", VerifyResetTokenView.as_view(), name="verify-reset-token"),
    path("reset-password/<str:token>/", ResetPasswordView.as_view(), name="reset-password"),
    # Profile Management (must be before router to avoid conflicts)
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("update-phone/", UpdatePhoneView.as_view(), name="update-phone"),
    path("update-phone-msg91/", UpdatePhoneMsg91View.as_view(), name="update-phone-msg91"),
    path("send-registration-otp/", SendRegistrationOTPView.as_view(), name="send-registration-otp"),
    path("verify-registration-otp/", VerifyRegistrationOTPView.as_view(), name="verify-registration-otp"),
    # Phone-based authentication (login + signup with OTP, no email/password needed)
    path("send-phone-auth-otp/", SendPhoneAuthOTPView.as_view(), name="send-phone-auth-otp"),
    path("phone-login/", PhoneLoginView.as_view(), name="phone-login"),
    path("phone-register/", PhoneRegisterView.as_view(), name="phone-register"),
    path("export-data/", ExportDataView.as_view(), name="export-data"),
    path("request-data-export/", RequestDataExportView.as_view(), name="request-data-export"),
    path("data-export/<uuid:token>/", DataExportDetailView.as_view(), name="data-export-detail"),
    path("data-export/<uuid:token>/pdf/", DataExportPDFView.as_view(), name="data-export-pdf"),
    path("delete-account/", DeleteAccountView.as_view(), name="delete-account"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("player/profile/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("player/profile/me/", CurrentPlayerProfileView.as_view(), name="current-player-profile"),
    path("host/profile/<int:pk>/", HostProfileView.as_view(), name="host-profile"),
    path("host/profile/me/", CurrentHostProfileView.as_view(), name="current-host-profile"),
    path("host/upload-aadhar/", UploadAadharView.as_view(), name="upload-aadhar"),
    # Search
    path("players/search/", PlayerUsernameSearchView.as_view(), name="player-username-search"),
    path("hosts/search/", HostSearchView.as_view(), name="host-search"),
    # Player Analytics
    path("players/analytics/stats/", PlayerAnalyticsStatsView.as_view(), name="player-analytics-stats"),
    path("players/analytics/trend/", PlayerAnalyticsTrendView.as_view(), name="player-analytics-trend"),
    path("players/analytics/activity/", PlayerAnalyticsActivityView.as_view(), name="player-analytics-activity"),
    path("players/analytics/weekly-activity/", PlayerAnalyticsWeeklyActivityView.as_view(), name="player-analytics-weekly-activity"),
    path("players/analytics/weekly-trend/", PlayerAnalyticsWeeklyTrendView.as_view(), name="player-analytics-weekly-trend"),
    path("players/analytics/recent-results/", PlayerAnalyticsRecentResultsView.as_view(), name="player-analytics-recent-results"),
    path("players/analytics/team-stats/", PlayerTeamAnalyticsView.as_view(), name="player-analytics-team-stats"),
    # Leaderboard
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("teams/<int:team_id>/rank/", TeamRankView.as_view(), name="team-rank"),
    # Invites (Invite-Based Registration Flow)
    path("invites/<str:token>/", RetrieveInviteDetailsView.as_view(), name="invite-details"),
    path("invites/<str:token>/accept/", AcceptInviteView.as_view(), name="invite-accept"),
    path("invites/<str:token>/decline/", DeclineInviteView.as_view(), name="invite-decline"),
    # Notifications
    path("notifications/", NotificationListView.as_view(), name="notifications-list"),
    path("notifications/mark-all-read/", NotificationMarkAllReadView.as_view(), name="notifications-mark-all-read"),
    path("notifications/bulk/", NotificationBulkActionView.as_view(), name="notifications-bulk"),
    path("notifications/<int:pk>/", NotificationDeleteView.as_view(), name="notification-delete"),
    path("notifications/<int:pk>/read/", NotificationMarkReadView.as_view(), name="notification-mark-read"),
    # Contact & Report
    path("contact/", ContactFormView.as_view(), name="contact-form"),
    path("report-issue/", ReportIssueView.as_view(), name="report-issue"),
    # Router URLs (must be last)
    path("", include(router.urls)),
]
