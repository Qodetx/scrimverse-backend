from .settings import *
import os

# Local override to use SQLite for quick local setup (temporary)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

# Use console email backend locally to avoid external email delivery
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
