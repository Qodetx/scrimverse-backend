from django.urls import path

from .views import (  # Tournament URLs; Scrim URLs; Registration URLs; Rating URLs
    HostRatingCreateView,
    HostRatingsListView,
    HostTournamentsView,
    PlayerScrimRegistrationsView,
    PlayerTournamentRegistrationsView,
    ScrimCreateView,
    ScrimDeleteView,
    ScrimDetailView,
    ScrimListView,
    ScrimRegistrationCreateView,
    ScrimUpdateView,
    TournamentCreateView,
    TournamentDeleteView,
    TournamentDetailView,
    TournamentListView,
    TournamentRegistrationCreateView,
    TournamentUpdateView,
)

urlpatterns = [
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
