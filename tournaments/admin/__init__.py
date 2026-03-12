# Import all submodules to trigger @admin.register() decorators.
# Django discovers admin classes by importing this package.

from tournaments.admin import tournament_admin  # noqa: F401
from tournaments.admin import rating_admin  # noqa: F401
from tournaments.admin import scoring_admin  # noqa: F401
