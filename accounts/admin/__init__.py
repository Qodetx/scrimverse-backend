# Import all submodules to trigger @admin.register() decorators.
# Django discovers admin classes by importing this package.

from accounts.admin import user_admin  # noqa: F401
from accounts.admin import profile_admin  # noqa: F401
from accounts.admin import team_admin  # noqa: F401
