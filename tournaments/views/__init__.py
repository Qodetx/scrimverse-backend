# Re-export all views so existing imports (e.g. urls.py) remain unchanged.

from tournaments.views.permissions import IsHostUser, IsPlayerUser  # noqa: F401

from tournaments.views.list import (  # noqa: F401
    TournamentListView,
    TournamentDetailView,
    HostTournamentsView,
    TournamentStatsView,
    PlatformStatsView,
    HostDashboardStatsView,
    HostAnalyticsView,
)

from tournaments.views.manage import (  # noqa: F401
    TournamentCreateView,
    TournamentUpdateView,
    TournamentDeleteView,
    BulkScheduleUpdateView,
    ManageTournamentView,
    UpdateTournamentFieldsView,
    UpdateTeamStatusView,
    StartTournamentView,
    EndTournamentView,
)

from tournaments.views.registration import (  # noqa: F401
    TournamentRegistrationInitiateView,
    TournamentRegistrationCreateView,
    PlayerTournamentRegistrationsView,
    PlayerPublicRegistrationsView,
    TournamentRegistrationsView,
    TournamentRegistrationExportView,
    SelectTeamsView,
)

from tournaments.views.rounds import (  # noqa: F401
    StartRoundView,
    SubmitRoundScoresView,
    EndRoundView,
    SelectWinnerView,
)

from tournaments.views.ratings import (  # noqa: F401
    HostRatingCreateView,
    HostRatingsListView,
)

from tournaments.views.groups import (  # noqa: F401
    ConfigureRoundView,
    RoundGroupsListView,
    RoundResultsView,
    RoundSlotListExportView,
)

from tournaments.views.matches import (  # noqa: F401
    StartMatchView,
    EndMatchView,
    UpdateMatchCredentialsView,
    SubmitMatchScoresView,
    GetTeamPlayersView,
)

from tournaments.views.sponsors import (  # noqa: F401
    TournamentSponsorListCreateView,
    TournamentSponsorDetailView,
)
