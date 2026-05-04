"""
Quick end-to-end verification of the per-member temporary team feature.

Run with:
    python manage.py shell < scripts/verify_per_member_temp.py

It creates ephemeral users/teams, runs each scenario, prints PASS/FAIL,
then cleans up. No DB pollution if run on a dev DB.
"""
from datetime import timedelta

from django.utils import timezone

from accounts.models import Notification, PlayerProfile, Team, TeamMember, User
from accounts.team_helpers import (
    determine_member_temp_status,
    has_permanent_team_for_game,
    is_team_temporary_for_user,
)

PREFIX = "_pmt_verify_"
RESULTS = []


def _record(label, passed, msg=""):
    RESULTS.append((label, passed, msg))
    flag = "PASS" if passed else "FAIL"
    print(f"  [{flag}] {label}{(' — ' + msg) if msg else ''}")


def _make_user(uname):
    u = User.objects.create_user(
        username=PREFIX + uname,
        email=f"{PREFIX}{uname}@example.com",
        password="x",
        user_type="player",
    )
    PlayerProfile.objects.get_or_create(user=u)
    return u


def cleanup():
    User.objects.filter(username__startswith=PREFIX).delete()
    Team.objects.filter(name__startswith=PREFIX).delete()
    Notification.objects.filter(user__username__startswith=PREFIX).delete()


# ---------------------------------------------------------------- Scenario 1
def scenario_helpers():
    print("\n[1] team_helpers basic checks")
    a = _make_user("a1")
    perm = Team.objects.create(
        name=PREFIX + "perm_a1", captain=a, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=perm, user=a, username=a.username, is_captain=True, is_temporary=False
    )

    _record("has_permanent_team_for_game(a, BGMI) == True",
            has_permanent_team_for_game(a, "BGMI") is True)
    _record("has_permanent_team_for_game(a, Valorant) == False",
            has_permanent_team_for_game(a, "Valorant") is False)

    is_t, deadline = determine_member_temp_status(a, "BGMI")
    _record("determine_member_temp_status(a, BGMI) returns temp",
            is_t is True and deadline is not None)
    is_t2, deadline2 = determine_member_temp_status(a, "Valorant")
    _record("determine_member_temp_status(a, Valorant) returns perm",
            is_t2 is False and deadline2 is None)


# ---------------------------------------------------------------- Scenario 2
def scenario_serializer():
    print("\n[2] Serializer is_temporary_for_me")
    from accounts.serializers import TeamSerializer

    captain = _make_user("cap2")
    other = _make_user("other2")
    team = Team.objects.create(
        name=PREFIX + "mixed", captain=captain, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    TeamMember.objects.create(
        team=team, user=other, username=other.username,
        is_captain=False, is_temporary=True,
        conversion_deadline=timezone.now() + timedelta(hours=48),
    )

    class FakeReq:
        def __init__(self, user):
            self.user = user
            self.user.is_authenticated = True

    s_captain = TeamSerializer(team, context={"request": FakeReq(captain)})
    s_other = TeamSerializer(team, context={"request": FakeReq(other)})

    _record("captain sees is_temporary_for_me == False",
            s_captain.data["is_temporary_for_me"] is False)
    _record("other sees is_temporary_for_me == True",
            s_other.data["is_temporary_for_me"] is True)
    _record("captain my_conversion_deadline is None",
            s_captain.data["my_conversion_deadline"] is None)
    _record("other my_conversion_deadline is set",
            s_other.data["my_conversion_deadline"] is not None)


# ---------------------------------------------------------------- Scenario 3
def scenario_convert_per_member():
    print("\n[3] convert_permanent — per-member path")
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounts.views.team import TeamViewSet

    captain = _make_user("cap3")
    member = _make_user("memb3")
    team = Team.objects.create(
        name=PREFIX + "convert", captain=captain, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    membership = TeamMember.objects.create(
        team=team, user=member, username=member.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )

    factory = APIRequestFactory()
    request = factory.post(f"/api/accounts/teams/{team.id}/convert_permanent/")
    force_authenticate(request, user=member)
    view = TeamViewSet.as_view({"post": "convert_permanent"})
    resp = view(request, pk=team.id)
    membership.refresh_from_db()

    _record("convert returns 200", resp.status_code == 200, f"got {resp.status_code}")
    _record("membership.is_temporary becomes False", membership.is_temporary is False)
    _record("membership.conversion_deadline cleared", membership.conversion_deadline is None)


# ---------------------------------------------------------------- Scenario 4
def scenario_convert_blocked_by_existing_perm():
    print("\n[4] convert_permanent — blocked when existing perm team")
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounts.views.team import TeamViewSet

    user = _make_user("conf4")
    # User already has a perm BGMI team
    existing = Team.objects.create(
        name=PREFIX + "existing", captain=user, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=existing, user=user, username=user.username,
        is_captain=True, is_temporary=False,
    )

    captain2 = _make_user("cap4")
    new_team = Team.objects.create(
        name=PREFIX + "new", captain=captain2, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=new_team, user=captain2, username=captain2.username,
        is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=new_team, user=user, username=user.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )

    factory = APIRequestFactory()
    request = factory.post(f"/api/accounts/teams/{new_team.id}/convert_permanent/")
    force_authenticate(request, user=user)
    view = TeamViewSet.as_view({"post": "convert_permanent"})
    resp = view(request, pk=new_team.id)

    _record("convert returns 409 conflict", resp.status_code == 409, f"got {resp.status_code}")
    if resp.status_code == 409:
        _record("conflict response includes existing team name",
                resp.data.get("conflict_team_name") == existing.name)


# ---------------------------------------------------------------- Scenario 5
def scenario_decline_member_removes():
    print("\n[5] decline_conversion — non-captain removed")
    from rest_framework.test import APIRequestFactory, force_authenticate
    from accounts.views.team import TeamViewSet

    captain = _make_user("cap5")
    member = _make_user("memb5")
    team = Team.objects.create(
        name=PREFIX + "decline", captain=captain, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    deadline = timezone.now() + timedelta(hours=48)
    TeamMember.objects.create(
        team=team, user=member, username=member.username,
        is_captain=False, is_temporary=True, conversion_deadline=deadline,
    )

    factory = APIRequestFactory()
    request = factory.post(f"/api/accounts/teams/{team.id}/decline_conversion/")
    force_authenticate(request, user=member)
    view = TeamViewSet.as_view({"post": "decline_conversion"})
    resp = view(request, pk=team.id)

    _record("decline returns 200", resp.status_code == 200, f"got {resp.status_code}")
    _record("membership removed",
            not TeamMember.objects.filter(team=team, user=member).exists())
    _record("team still exists", Team.objects.filter(id=team.id).exists())


# ---------------------------------------------------------------- Scenario 6
def scenario_cleanup_per_member():
    print("\n[6] cleanup_expired_temp_teams — per-member expiry")
    from tournaments.tasks.tournament_tasks import cleanup_expired_temp_teams

    captain = _make_user("cap6")
    member = _make_user("memb6")
    team = Team.objects.create(
        name=PREFIX + "cleanup", captain=captain, is_temporary=False, game="BGMI"
    )
    TeamMember.objects.create(
        team=team, user=captain, username=captain.username,
        is_captain=True, is_temporary=False,
    )
    expired = TeamMember.objects.create(
        team=team, user=member, username=member.username,
        is_captain=False, is_temporary=True,
        conversion_deadline=timezone.now() - timedelta(hours=1),
    )

    cleanup_expired_temp_teams()

    _record("expired membership deleted",
            not TeamMember.objects.filter(id=expired.id).exists())
    _record("team kept (captain still there)",
            Team.objects.filter(id=team.id).exists())
    _record("captain membership preserved",
            TeamMember.objects.filter(team=team, user=captain).exists())


# ---------------------------------------------------------------- Run
def main():
    cleanup()
    try:
        scenario_helpers()
        scenario_serializer()
        scenario_convert_per_member()
        scenario_convert_blocked_by_existing_perm()
        scenario_decline_member_removes()
        scenario_cleanup_per_member()
    finally:
        cleanup()

    print("\n" + "=" * 60)
    total = len(RESULTS)
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = total - passed
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    if failed:
        print("\nFailures:")
        for label, p, msg in RESULTS:
            if not p:
                print(f"  - {label}{(' — ' + msg) if msg else ''}")


main()
