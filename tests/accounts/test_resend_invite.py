"""
Tests for the resend_invite endpoint and invited_members serializer field.

Covers:
  - Serializer exposes pending / rejected / expired invites under `invited_members`
  - Resend endpoint sends correctly for email / phone / username invite types
  - Resend rejects when invite is already accepted
  - Resend resets a rejected invite back to pending
  - Resend extends invite_expires_at by 7 days
  - Captain-only enforcement
  - Rate limit kicks in after 3 resends per 30-minute window
"""
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status

from accounts.models import Notification, Team, TeamJoinRequest, TeamMember, User
from tests.factories import PlayerProfileFactory, UserFactory


# ───────────────────────── helpers ─────────────────────────


def _make_team(captain, name="Resend Test Team", game="BGMI"):
    team = Team.objects.create(
        name=name, captain=captain, is_temporary=False, game=game,
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    return team


def _make_invite(team, invite_type, status_value="pending", **kwargs):
    defaults = {
        "team": team,
        "request_type": "invite",
        "status": status_value,
        "invite_type": invite_type,
        "invite_token": "tok-" + invite_type + "-" + status_value,
        "invite_expires_at": timezone.now() + timedelta(days=7),
    }
    defaults.update(kwargs)
    return TeamJoinRequest.objects.create(**defaults)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset rate-limit counters between tests."""
    cache.clear()
    yield
    cache.clear()


# ───────────────────────── serializer ─────────────────────────


@pytest.mark.django_db
def test_invited_members_includes_pending_rejected_expired(authenticated_client, player_user):
    team = _make_team(player_user)
    pending = _make_invite(team, "email", "pending", invited_email="a@example.com")
    rejected = _make_invite(team, "phone", "rejected", phone_number="+919876543210")
    expired = _make_invite(team, "username", "expired", player=UserFactory(user_type="player", username="exp_user"))
    # Accepted should NOT appear
    _make_invite(team, "email", "accepted", invited_email="acc@example.com")

    response = authenticated_client.get(f"/api/accounts/teams/{team.id}/")
    assert response.status_code == 200
    invited = response.data["invited_members"]
    assert len(invited) == 3
    ids = {item["id"] for item in invited}
    assert pending.id in ids
    assert rejected.id in ids
    assert expired.id in ids


@pytest.mark.django_db
def test_invited_members_returns_correct_identifier_per_type(authenticated_client, player_user):
    team = _make_team(player_user)
    invitee = UserFactory(user_type="player", username="invitee_u")
    PlayerProfileFactory(user=invitee)

    _make_invite(team, "email", "pending", invited_email="EMAIL@X.com")
    _make_invite(team, "phone", "pending", phone_number="+911234567890")
    _make_invite(team, "username", "pending", player=invitee)

    response = authenticated_client.get(f"/api/accounts/teams/{team.id}/")
    invited = response.data["invited_members"]
    by_type = {x["invite_type"]: x for x in invited}
    assert by_type["email"]["identifier"] == "EMAIL@X.com"
    assert by_type["phone"]["identifier"] == "+911234567890"
    assert by_type["username"]["identifier"] == "invitee_u"


# ───────────────────────── resend endpoint ─────────────────────────


@pytest.mark.django_db
def test_resend_invite_email_calls_send_helper(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(team, "email", "pending", invited_email="x@example.com")

    with mock.patch("scrimverse.email_utils.send_team_invite_email") as send_mock:
        response = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
    assert response.status_code == 200, response.data
    send_mock.assert_called_once()
    kwargs = send_mock.call_args.kwargs
    assert kwargs["invited_email"] == "x@example.com"
    assert kwargs["team_name"] == team.name
    assert kwargs["invite_token"] == invite.invite_token


@pytest.mark.django_db
def test_resend_invite_phone_calls_sms_helper(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(team, "phone", "pending", phone_number="+919812345678")

    with mock.patch("scrimverse.sms_utils.send_team_invite_sms") as sms_mock:
        response = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
    assert response.status_code == 200, response.data
    sms_mock.assert_called_once()
    kwargs = sms_mock.call_args.kwargs
    assert kwargs["phone_number"] == "+919812345678"
    assert kwargs["invite_token"] == invite.invite_token


@pytest.mark.django_db
def test_resend_invite_username_creates_notification(authenticated_client, player_user):
    team = _make_team(player_user)
    invitee = UserFactory(user_type="player", username="recv_user")
    PlayerProfileFactory(user=invitee)
    invite = _make_invite(team, "username", "pending", player=invitee)

    Notification.objects.filter(user=invitee).delete()
    response = authenticated_client.post(
        f"/api/accounts/teams/{team.id}/resend_invite/",
        {"invite_id": invite.id}, format="json",
    )
    assert response.status_code == 200, response.data
    assert Notification.objects.filter(user=invitee, type="team_invite").exists()


@pytest.mark.django_db
def test_resend_invite_resets_rejected_to_pending(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(team, "email", "rejected", invited_email="r@example.com")

    with mock.patch("scrimverse.email_utils.send_team_invite_email"):
        response = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
    assert response.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "pending"


@pytest.mark.django_db
def test_resend_invite_resets_expired_to_pending(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(
        team, "email", "expired",
        invited_email="e@example.com",
        invite_expires_at=timezone.now() - timedelta(days=1),
    )
    with mock.patch("scrimverse.email_utils.send_team_invite_email"):
        response = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
    assert response.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "pending"
    # New expiry should be ~7 days in the future
    assert invite.invite_expires_at > timezone.now() + timedelta(days=6)


@pytest.mark.django_db
def test_resend_invite_extends_expiry(authenticated_client, player_user):
    team = _make_team(player_user)
    original_expiry = timezone.now() + timedelta(days=2)
    invite = _make_invite(
        team, "email", "pending",
        invited_email="t@example.com",
        invite_expires_at=original_expiry,
    )
    with mock.patch("scrimverse.email_utils.send_team_invite_email"):
        response = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
    assert response.status_code == 200
    invite.refresh_from_db()
    assert invite.invite_expires_at > original_expiry


@pytest.mark.django_db
def test_resend_invite_rejects_when_already_accepted(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(team, "email", "accepted", invited_email="acc@example.com")
    response = authenticated_client.post(
        f"/api/accounts/teams/{team.id}/resend_invite/",
        {"invite_id": invite.id}, format="json",
    )
    assert response.status_code == 400
    assert "already" in str(response.data).lower()


@pytest.mark.django_db
def test_resend_invite_404_for_unknown_id(authenticated_client, player_user):
    team = _make_team(player_user)
    response = authenticated_client.post(
        f"/api/accounts/teams/{team.id}/resend_invite/",
        {"invite_id": 99999999}, format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_resend_invite_403_for_non_captain(authenticated_client, player_user):
    """A non-captain team member cannot resend invites."""
    captain = UserFactory(user_type="player", username="other_cap")
    PlayerProfileFactory(user=captain)
    team = _make_team(captain)
    # Add player_user as a regular member (not captain)
    TeamMember.objects.create(
        team=team, user=player_user, username=player_user.username,
        is_captain=False, is_temporary=False,
    )
    invite = _make_invite(team, "email", "pending", invited_email="m@example.com")

    response = authenticated_client.post(
        f"/api/accounts/teams/{team.id}/resend_invite/",
        {"invite_id": invite.id}, format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_resend_invite_rate_limit_after_3(authenticated_client, player_user):
    team = _make_team(player_user)
    invite = _make_invite(team, "email", "pending", invited_email="rl@example.com")

    with mock.patch("scrimverse.email_utils.send_team_invite_email"):
        for i in range(3):
            r = authenticated_client.post(
                f"/api/accounts/teams/{team.id}/resend_invite/",
                {"invite_id": invite.id}, format="json",
            )
            assert r.status_code == 200, f"attempt {i + 1}: {r.data}"

        # 4th attempt should be rate-limited
        r = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
        assert r.status_code == 429
        assert r.data["error"] == "rate_limited"


@pytest.mark.django_db
def test_resend_invite_send_failure_rolls_back_counter(authenticated_client, player_user):
    """If the send helper raises, the rate-limit counter shouldn't burn a try."""
    team = _make_team(player_user)
    invite = _make_invite(team, "email", "pending", invited_email="fail@example.com")

    # First: a failing send
    with mock.patch(
        "scrimverse.email_utils.send_team_invite_email",
        side_effect=Exception("boom"),
    ):
        r1 = authenticated_client.post(
            f"/api/accounts/teams/{team.id}/resend_invite/",
            {"invite_id": invite.id}, format="json",
        )
        assert r1.status_code == 502

    # Then: 3 successful sends should still all succeed (counter wasn't burned)
    with mock.patch("scrimverse.email_utils.send_team_invite_email"):
        for i in range(3):
            r = authenticated_client.post(
                f"/api/accounts/teams/{team.id}/resend_invite/",
                {"invite_id": invite.id}, format="json",
            )
            assert r.status_code == 200, f"after-failure attempt {i + 1}: {r.data}"
