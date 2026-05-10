from django.urls import path

from .views import CommunityJoinView, CommunitySettingsView, CommunityStatusView

urlpatterns = [
    path("settings/", CommunitySettingsView.as_view(), name="community-settings"),
    path("join/", CommunityJoinView.as_view(), name="community-join"),
    path("status/", CommunityStatusView.as_view(), name="community-status"),
]
