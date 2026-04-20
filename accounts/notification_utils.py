"""
Helper to check if a user has a specific notification preference enabled.
Returns True (send notification) if preference is enabled or not set (default on).
"""
from .models import PlayerProfile


PREF_DEFAULTS = {
    'enableNotifications': True,
    'matchReminders': True,
    'tournamentUpdates': True,
    'teamInvites': True,
    'marketingEmails': False,
}


def should_notify(user, pref_key):
    """
    Returns True if the notification should be sent to the user.
    - If enableNotifications is False, suppress ALL notifications.
    - Otherwise check the specific pref_key.
    - Defaults to True for unknown keys (send by default).
    """
    try:
        profile = PlayerProfile.objects.get(user=user)
        prefs = profile.notification_preferences or {}
    except PlayerProfile.DoesNotExist:
        return PREF_DEFAULTS.get(pref_key, True)

    # Master switch — if disabled, suppress everything
    if not prefs.get('enableNotifications', True):
        return False

    return prefs.get(pref_key, PREF_DEFAULTS.get(pref_key, True))
