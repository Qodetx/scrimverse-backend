# Re-export all views so existing imports (e.g. urls.py) remain unchanged.

from accounts.views.auth import (  # noqa: F401
    PlayerRegistrationView,
    HostRegistrationView,
    LoginView,
    GoogleAuthView,
    CurrentUserView,
    ChangePasswordView,
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
    ExportDataView,
    DeleteAccountView,
    RequestDataExportView,
    DataExportDetailView,
    DataExportPDFView,
)

from accounts.views.team import (  # noqa: F401
    IsPlayerUser,
    TeamViewSet,
    RetrieveInviteDetailsView,
    AcceptInviteView,
    DeclineInviteView,
)

from accounts.views.otp_views import (  # noqa: F401
    SendOTPView,
    UpdatePhoneView,
    UpdatePhoneMsg91View,
    SendRegistrationOTPView,
    VerifyRegistrationOTPView,
)

from accounts.views.phone_auth import (  # noqa: F401
    SendPhoneAuthOTPView,
    PhoneLoginView,
    PhoneRegisterView,
)
