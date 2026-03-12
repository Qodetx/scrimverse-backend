# Re-export all views so existing imports (e.g. urls.py) remain unchanged.

from accounts.views.auth import (  # noqa: F401
    PlayerRegistrationView,
    HostRegistrationView,
    LoginView,
    GoogleAuthView,
    CurrentUserView,
)

from accounts.views.profile import (  # noqa: F401
    PlayerProfileView,
    CurrentPlayerProfileView,
    HostProfileView,
    CurrentHostProfileView,
    UploadAadharView,
    UserDetailView,
    PlayerUsernameSearchView,
    HostSearchView,
)

from accounts.views.team import (  # noqa: F401
    IsPlayerUser,
    TeamViewSet,
    RetrieveInviteDetailsView,
    AcceptInviteView,
    DeclineInviteView,
)
