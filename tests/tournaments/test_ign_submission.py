"""
Tests for SubmitIGNView — captain IGN submission flow.

Covers the semifinals re-enable requirements:
- captain can submit partial IGNs (1..N) on an ongoing tournament
- already-submitted IGNs can be edited and re-submitted (no auto-lock)
- locked registrations stay editable WHILE the tournament is ongoing
- locked registrations are still blocked once the tournament is completed
- only the captain may submit
- submitting a known username updates that player's profile IGN
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import PlayerProfile, User
from tests.factories import (
    PlayerProfileFactory,
    TournamentFactory,
    TournamentRegistrationFactory,
    UserFactory,
)


def _url(tournament_id, registration_id):
    return f"/api/tournaments/{tournament_id}/registrations/{registration_id}/submit-ign/"


@pytest.fixture
def captain_user(db):
    user = UserFactory(user_type="player", username="captain_ign")
    PlayerProfileFactory(user=user)
    return user


@pytest.fixture
def ongoing(db, host_user):
    return TournamentFactory(host=host_user.host_profile, status="ongoing", game_name="BGMI")


@pytest.fixture
def registration(db, ongoing, captain_user):
    return TournamentRegistrationFactory(
        tournament=ongoing,
        player=captain_user.player_profile,
        team_name="Test Squad",
        team_members=[{"username": "captain_ign", "is_registered": True, "player_id": captain_user.id}],
        ign_submissions={},
        ign_locked=False,
    )


@pytest.mark.django_db
def test_captain_partial_submit(captain_user, registration):
    """Captain can submit a single IGN; nothing gets locked."""
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "CaptainIGN1"}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.ign_submissions == {"captain_ign": "CaptainIGN1"}
    assert registration.ign_locked is False
    assert res.data["saved_count"] == 1


@pytest.mark.django_db
def test_generic_slot_keys_collected(captain_user, registration):
    """Captain of a broken-snapshot team can still submit teammate IGNs under
    positional keys (player_2..player_4) — they are simply collected."""
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {
            "ign_submissions": {
                "captain_ign": "CapIGN",
                "player_2": "Mate2",
                "player_3": "Mate3",
                "player_4": "Mate4",
            }
        },
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.ign_submissions == {
        "captain_ign": "CapIGN",
        "player_2": "Mate2",
        "player_3": "Mate3",
        "player_4": "Mate4",
    }


@pytest.mark.django_db
def test_resubmit_edits_existing(captain_user, registration):
    """Re-submitting overwrites an existing IGN and merges new ones."""
    registration.ign_submissions = {"captain_ign": "OldIGN", "player_2": "Keep2"}
    registration.save()
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "NewIGN", "player_3": "Add3"}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.ign_submissions == {
        "captain_ign": "NewIGN",  # overwritten
        "player_2": "Keep2",  # preserved
        "player_3": "Add3",  # added
    }


@pytest.mark.django_db
def test_locked_registration_editable_while_ongoing(captain_user, registration):
    """A locked registration is STILL editable while the tournament is ongoing."""
    registration.ign_locked = True
    registration.ign_submissions = {"captain_ign": "OldLocked"}
    registration.save()
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "CorrectedIGN"}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.ign_submissions["captain_ign"] == "CorrectedIGN"


@pytest.mark.django_db
def test_locked_registration_blocked_when_completed(captain_user, registration):
    """Once the tournament is completed, a locked registration is blocked again."""
    registration.ign_locked = True
    registration.save()
    registration.tournament.status = "completed"
    registration.tournament.save()
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "Nope"}},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_non_captain_cannot_submit(registration):
    """A non-captain user cannot submit IGNs for the registration."""
    other = UserFactory(user_type="player", username="not_captain")
    PlayerProfileFactory(user=other)
    client = APIClient()
    client.force_authenticate(user=other)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "Hack"}},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_known_username_updates_profile_ign(captain_user, registration):
    """Submitting an IGN keyed by a real username updates that player's profile."""
    mate = UserFactory(user_type="player", username="realmate")
    PlayerProfileFactory(user=mate)
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"realmate": "MateBGMI"}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    mate.player_profile.refresh_from_db()
    assert mate.player_profile.game_profiles.get("BGMI", {}).get("ign") == "MateBGMI"


@pytest.mark.django_db
def test_empty_values_skipped(captain_user, registration):
    """Blank IGNs are ignored, not stored."""
    client = APIClient()
    client.force_authenticate(user=captain_user)
    res = client.post(
        _url(registration.tournament_id, registration.id),
        {"ign_submissions": {"captain_ign": "Real", "player_2": "   ", "player_3": ""}},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    registration.refresh_from_db()
    assert registration.ign_submissions == {"captain_ign": "Real"}
