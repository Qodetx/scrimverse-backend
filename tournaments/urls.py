from django.urls import path

# Groups and Matches Views
from .groups_views import (
    ConfigureRoundView,
    EndMatchView,
    RoundGroupsListView,
    RoundResultsView,
    StartMatchView,
    SubmitMatchScoresView,
)
from .views import (  # Tournament URLs; Scrim URLs; Registration URLs; Rating URLs
    EndRoundView,
    EndTournamentView,
    HostDashboardStatsView,
    HostRatingCreateView,
    HostRatingsListView,
    HostTournamentsView,
    ManageTournamentView,
    PlatformStatsView,
    PlayerScrimRegistrationsView,
    PlayerTournamentRegistrationsView,
    ScrimCreateView,
    ScrimDeleteView,
    ScrimDetailView,
    ScrimListView,
    ScrimRegistrationCreateView,
    ScrimUpdateView,
    SelectTeamsView,
    SelectWinnerView,
    StartRoundView,
    StartTournamentView,
    SubmitRoundScoresView,
    TournamentCreateView,
    TournamentDeleteView,
    TournamentDetailView,
    TournamentListView,
    TournamentRegistrationCreateView,
    TournamentRegistrationsView,
    TournamentStatsView,
    TournamentUpdateView,
    UpdateTeamStatusView,
    UpdateTournamentFieldsView,
)

urlpatterns = [
    # Platform Stats
    path("stats/platform/", PlatformStatsView.as_view(), name="platform-stats"),
    path("stats/host/", HostDashboardStatsView.as_view(), name="host-stats"),
    # Tournament endpoints
    path("", TournamentListView.as_view(), name="tournament-list"),
    path("<int:pk>/", TournamentDetailView.as_view(), name="tournament-detail"),
    path("create/", TournamentCreateView.as_view(), name="tournament-create"),
    path("<int:pk>/update/", TournamentUpdateView.as_view(), name="tournament-update"),
    path("<int:pk>/delete/", TournamentDeleteView.as_view(), name="tournament-delete"),
    path("host/<int:host_id>/", HostTournamentsView.as_view(), name="host-tournaments"),
    # Tournament Registration
    path("<int:tournament_id>/register/", TournamentRegistrationCreateView.as_view(), name="tournament-register"),
    path("my-registrations/", PlayerTournamentRegistrationsView.as_view(), name="my-tournament-registrations"),
    # Tournament Management
    path("<int:pk>/manage/", ManageTournamentView.as_view(), name="tournament-manage"),
    path("<int:pk>/update-fields/", UpdateTournamentFieldsView.as_view(), name="tournament-update-fields"),
    path("<int:tournament_id>/registrations/", TournamentRegistrationsView.as_view(), name="tournament-registrations"),
    path(
        "<int:tournament_id>/registrations/<int:registration_id>/status/",
        UpdateTeamStatusView.as_view(),
        name="update-team-status",
    ),
    path("<int:tournament_id>/start/", StartTournamentView.as_view(), name="start-tournament"),
    path("<int:tournament_id>/start-round/<int:round_number>/", StartRoundView.as_view(), name="start-round"),
    path("<int:tournament_id>/submit-scores/", SubmitRoundScoresView.as_view(), name="submit-scores"),
    path("<int:tournament_id>/select-teams/", SelectTeamsView.as_view(), name="select-teams"),
    path("<int:tournament_id>/end-round/", EndRoundView.as_view(), name="end-round"),
    path("<int:tournament_id>/select-winner/", SelectWinnerView.as_view(), name="select-winner"),
    path("<int:tournament_id>/stats/", TournamentStatsView.as_view(), name="tournament-stats"),
    path("<int:tournament_id>/end/", EndTournamentView.as_view(), name="end-tournament"),
    # Groups and Matches Management (NEW)
    path(
        "<int:tournament_id>/rounds/<int:round_number>/configure/", ConfigureRoundView.as_view(), name="configure-round"
    ),
    path(
        "<int:tournament_id>/rounds/<int:round_number>/groups/", RoundGroupsListView.as_view(), name="round-groups-list"
    ),
    path("<int:tournament_id>/rounds/<int:round_number>/results/", RoundResultsView.as_view(), name="round-results"),
    # Match Management (Old Implementation)
    path("<int:tournament_id>/groups/<int:group_id>/matches/start/", StartMatchView.as_view(), name="start-match"),
    path("<int:tournament_id>/matches/<int:match_id>/end/", EndMatchView.as_view(), name="end-match"),
    path(
        "<int:tournament_id>/matches/<int:match_id>/scores/",
        SubmitMatchScoresView.as_view(),
        name="submit-match-scores",
    ),
    # Scrim endpoints
    path("scrims/", ScrimListView.as_view(), name="scrim-list"),
    path("scrims/<int:pk>/", ScrimDetailView.as_view(), name="scrim-detail"),
    path("scrims/create/", ScrimCreateView.as_view(), name="scrim-create"),
    path("scrims/<int:pk>/update/", ScrimUpdateView.as_view(), name="scrim-update"),
    path("scrims/<int:pk>/delete/", ScrimDeleteView.as_view(), name="scrim-delete"),
    # Scrim Registration
    path("scrims/<int:scrim_id>/register/", ScrimRegistrationCreateView.as_view(), name="scrim-register"),
    path("scrims/my-registrations/", PlayerScrimRegistrationsView.as_view(), name="my-scrim-registrations"),
    # Host Rating
    path("host/<int:host_id>/rate/", HostRatingCreateView.as_view(), name="host-rate"),
    path("host/<int:host_id>/ratings/", HostRatingsListView.as_view(), name="host-ratings"),
]
