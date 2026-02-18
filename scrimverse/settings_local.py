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

# Note:
# settings (EMAIL_BACKEND, EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, etc.)
# are read from environment (.env). For local development, set these EMAIL_* vars directly
# in your .env to use your preferred SMTP provider (e.g., smtp.gmail.com). No extra LOCAL_*
# variables are required.
