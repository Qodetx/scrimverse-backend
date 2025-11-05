from django.urls import path

from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CurrentUserView,
    HostProfileView,
    HostRegistrationView,
    LoginView,
    PlayerProfileView,
    PlayerRegistrationView,
)

urlpatterns = [
    # Authentication
    path("player/register/", PlayerRegistrationView.as_view(), name="player-register"),
    path("host/register/", HostRegistrationView.as_view(), name="host-register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Profile Management
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("player/profile/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("host/profile/<int:pk>/", HostProfileView.as_view(), name="host-profile"),
]
