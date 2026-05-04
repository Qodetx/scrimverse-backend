"""
Helpers for the per-member temporary team logic.

Background:
    Originally `is_temporary` was a flag on the Team itself. The whole team
    was considered temporary if it was created from a tournament registration
    by a captain who didn't already have a permanent team. After 48h the
    captain had to convert or decline the team for everyone.

    Per-client requirement: the temporary status should be PER MEMBER:
      - If a member did not have a permanent team for the game, this team
        becomes their permanent team (is_temporary=False on their membership).
      - If a member already had a permanent team for the game, this team is
        only "temporary" for them — they get the convert-or-decline prompt.

    Legacy temp teams (Team.is_temporary=True) keep working as before — the
    helpers here gracefully handle both old-style and new-style data.
"""

from datetime import timedelta

from django.utils import timezone


# 48h window for an individual member to decide convert vs decline
MEMBER_CONVERSION_WINDOW = timedelta(hours=48)


def has_permanent_team_for_game(user, game):
    """
    Returns True if `user` already has a permanent team for `game`.

    A team membership counts as a "permanent team" when:
      - The team itself is not legacy-temporary (Team.is_temporary=False), AND
      - The membership itself is not temporary (TeamMember.is_temporary=False), AND
      - The team's game matches.
    """
    if not user or not game:
        return False
    from accounts.models import TeamMember  # avoid circular import
    return TeamMember.objects.filter(
        user=user,
        is_temporary=False,
        team__is_temporary=False,
        team__game=game,
    ).exists()


def determine_member_temp_status(user, game, tournament=None):
    """
    Given a user joining a team for `game`, return (is_temporary, conversion_deadline).

    If the user already has a permanent team for that game, this membership
    is temporary and gets a 48h conversion window starting from the
    tournament's registration_end (if available) or now.
    """
    if has_permanent_team_for_game(user, game):
        # Anchor deadline to tournament registration_end when known so all
        # members of the same registration share a similar timing.
        anchor = (
            tournament.registration_end
            if tournament and getattr(tournament, "registration_end", None)
            else timezone.now()
        )
        return True, anchor + MEMBER_CONVERSION_WINDOW
    return False, None


def is_team_temporary_for_user(team, user):
    """
    Returns True if `team` should be displayed as temporary for `user`.

    Considers both the legacy Team.is_temporary flag AND the new per-member
    TeamMember.is_temporary flag.
    """
    if not team or not user:
        return False
    if getattr(team, "is_temporary", False):
        return True  # legacy team: temp for everyone

    from accounts.models import TeamMember
    return TeamMember.objects.filter(
        team=team, user=user, is_temporary=True
    ).exists()
