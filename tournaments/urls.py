from django.urls import path

from tournaments.pricing_views import PlanPricingView
from tournaments.views import (  # Tournament URLs; Registration URLs; Rating URLs; Groups/Matches URLs
    TournamentSponsorListCreateView,
    TournamentSponsorDetailView,
    EndRoundView,
    EndTournamentView,
    HostDashboardStatsView,
    HostAnalyticsView,
    HostRatingCreateView,
    HostRatingsListView,
    HostTournamentsView,
    ManageTournamentView,
    PlatformStatsView,
    PlayerPublicRegistrationsView,
    PlayerTournamentRegistrationsView,
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
    TournamentRegistrationExportView,
    TournamentRegistrationInitiateView,
    TournamentRegistrationsView,
    TournamentStatsView,
    TournamentUpdateView,
    BulkScheduleUpdateView,
    UpdateTeamStatusView,
    UpdateTournamentFieldsView,
    ConfigureRoundView,
    RoundGroupsListView,
    RoundResultsView,
    RoundSlotListExportView,
    ShuffleGroupsView,
    StartMatchView,
    EndMatchView,
    UpdateMatchCredentialsView,
    SubmitMatchScoresView,
    GetTeamPlayersView,
    SubmitIGNView,
)

urlpatterns = [
    # Plan Pricing (Public)
    path("plan-pricing/", PlanPricingView.as_view(), name="plan-pricing"),
    # Platform Stats
    path("stats/platform/", PlatformStatsView.as_view(), name="platform-stats"),
    path("stats/host/", HostDashboardStatsView.as_view(), name="host-stats"),
    path("stats/host/analytics/", HostAnalyticsView.as_view(), name="host-analytics"),
    # Tournament endpoints
    path("", TournamentListView.as_view(), name="tournament-list"),
    path("<int:pk>/", TournamentDetailView.as_view(), name="tournament-detail"),
    path("create/", TournamentCreateView.as_view(), name="tournament-create"),
    path("<int:pk>/update/", TournamentUpdateView.as_view(), name="tournament-update"),
    path("<int:pk>/delete/", TournamentDeleteView.as_view(), name="tournament-delete"),
    path("<int:pk>/bulk-schedule/", BulkScheduleUpdateView.as_view(), name="tournament-bulk-schedule"),
    path("host/<int:host_id>/", HostTournamentsView.as_view(), name="host-tournaments"),
    # Tournament Registration - NEW INVITE-BASED FLOW
    path("<int:tournament_id>/register-init/", TournamentRegistrationInitiateView.as_view(), name="tournament-register-init"),
    path("<int:tournament_id>/register/", TournamentRegistrationCreateView.as_view(), name="tournament-register"),
    path("my-registrations/", PlayerTournamentRegistrationsView.as_view(), name="my-tournament-registrations"),
    path(
        "player/<int:player_id>/registrations/",
        PlayerPublicRegistrationsView.as_view(),
        name="player-public-registrations",
    ),
    # Tournament Management
    path("<int:pk>/manage/", ManageTournamentView.as_view(), name="tournament-manage"),
    path("<int:pk>/update-fields/", UpdateTournamentFieldsView.as_view(), name="tournament-update-fields"),
    path("<int:tournament_id>/registrations/", TournamentRegistrationsView.as_view(), name="tournament-registrations"),
    path("<int:tournament_id>/registrations/export/", TournamentRegistrationExportView.as_view(), name="tournament-registrations-export"),
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
    path(
        "<int:tournament_id>/rounds/<int:round_number>/slots/export/",
        RoundSlotListExportView.as_view(),
        name="round-slots-export",
    ),
    path(
        "<int:tournament_id>/rounds/<int:round_number>/shuffle/",
        ShuffleGroupsView.as_view(),
        name="shuffle-groups",
    ),
    # Match Management (Old Implementation)
    path("<int:tournament_id>/groups/<int:group_id>/matches/start/", StartMatchView.as_view(), name="start-match"),
    path("<int:tournament_id>/matches/<int:match_id>/end/", EndMatchView.as_view(), name="end-match"),
    path("<int:tournament_id>/matches/<int:match_id>/credentials/", UpdateMatchCredentialsView.as_view(), name="update-match-credentials"),
    path(
        "<int:tournament_id>/matches/<int:match_id>/scores/",
        SubmitMatchScoresView.as_view(),
        name="submit-match-scores",
    ),
    # Team Players
    path(
        "<int:tournament_id>/teams/<int:registration_id>/players/",
        GetTeamPlayersView.as_view(),
        name="get-team-players",
    ),
    # IGN Submission
    path(
        "<int:tournament_id>/registrations/<int:registration_id>/submit-ign/",
        SubmitIGNView.as_view(),
        name="submit-ign",
    ),
    # Host Rating
    path("host/<int:host_id>/rate/", HostRatingCreateView.as_view(), name="host-rate"),
    path("host/<int:host_id>/ratings/", HostRatingsListView.as_view(), name="host-ratings"),

    # Sponsors
    path("<int:tournament_id>/sponsors/", TournamentSponsorListCreateView.as_view(), name="tournament-sponsors"),
    path("<int:tournament_id>/sponsors/<int:sponsor_id>/", TournamentSponsorDetailView.as_view(), name="tournament-sponsor-detail"),
]
