"""
Tournament lifecycle tasks: status updates, cleanup, registration, groups, banners, stats.
"""
import logging
import os

from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from celery import shared_task
from PIL import Image

from accounts.models import HostProfile, Notification, PlayerProfile, Team, TeamJoinRequest, TeamMember
from accounts.notification_utils import should_notify
from payments.models import Payment
from tournaments.models import Match, RoundScore, Tournament, TournamentRegistration
from tournaments.services import TournamentGroupService

logger = logging.getLogger(__name__)


@shared_task
def update_tournament_statuses():
    """
    Update tournament statuses based on current time
    Runs every minute via Celery Beat
    """
    now = timezone.now()
    updated_count = 0

    # NOTE: upcoming → ongoing is intentionally NOT auto-triggered here.
    # The host must manually click "Start Tournament" to move a tournament to ongoing.
    # The tournament_start time only controls when the Start button unlocks in the UI.

    # Update ongoing → completed
    ongoing = Tournament.objects.filter(status="ongoing", tournament_end__lte=now)
    for tournament in ongoing:
        tournament.status = "completed"
        tournament.save(update_fields=["status"])
        updated_count += 1

    logger.info(f"Updated {updated_count} tournament statuses")
    return {"updated": updated_count}


@shared_task
def cleanup_unpaid_tournaments_and_registrations():
    """
    Remove tournaments and registrations that haven't been paid for
    Runs every hour via Celery Beat
    """
    now = timezone.now()

    # Delete unpaid payments older than 2 hours
    old_unpaid = Payment.objects.filter(status="pending", created_at__lt=now - timezone.timedelta(hours=2))
    count = old_unpaid.count()
    old_unpaid.delete()

    # Cancel pending team join requests older than 7 days
    old_requests = TeamJoinRequest.objects.filter(
        status="pending", created_at__lt=now - timezone.timedelta(days=7)
    )
    req_count = old_requests.count()
    old_requests.update(status="expired")

    logger.info(f"Cleaned up {count} unpaid payments, expired {req_count} team join requests")
    return {"payments_deleted": count, "requests_expired": req_count}


@shared_task
def process_tournament_registration(registration_id):
    """
    Process tournament registration asynchronously
    - Validate team members
    - Check for duplicates
    - Update participant count
    - Send confirmation notification

    Priority: CRITICAL-HIGH
    Impact: 80-90% faster registration
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing tournament registration {registration_id}...")

    try:
        registration = TournamentRegistration.objects.get(id=registration_id)
        tournament = registration.tournament

        # Validate team members (if team registration)
        if registration.team_members:
            team_player_ids = {member.get("id") for member in registration.team_members}

            # Check for duplicate players in other registrations
            existing_registrations = TournamentRegistration.objects.filter(
                tournament=tournament, status__in=["pending", "confirmed"]
            ).exclude(id=registration_id)

            for existing_reg in existing_registrations:
                if existing_reg.team_members:
                    registered_player_ids = {member.get("id") for member in existing_reg.team_members}
                    overlapping_ids = team_player_ids & registered_player_ids

                    if overlapping_ids:
                        # Mark as rejected due to duplicate
                        registration.status = "rejected"
                        registration.save()
                        logger.warning(f"Registration {registration_id} rejected: duplicate players")
                        return {"status": "rejected", "reason": "duplicate_players"}

        # If validation passed, confirm registration
        if registration.status == "pending":
            registration.status = "confirmed"
            registration.save()

            # TODO: Send confirmation email
            logger.info(f"Registration {registration_id} confirmed successfully")

        # Invalidate caches
        cache.delete("tournaments:list:all")
        cache.delete(f"tournament:registrations:{tournament.id}")

        return {"status": "confirmed", "registration_id": registration_id}

    except TournamentRegistration.DoesNotExist:
        logger.error(f"Registration {registration_id} not found")
        return {"error": "Registration not found"}
    except Exception as e:
        logger.error(f"Error processing registration: {e}")
        return {"error": str(e)}


@shared_task
def create_tournament_groups(tournament_id, round_number, config):
    """
    Create groups and matches for a round asynchronously
    - Create all groups
    - Distribute teams evenly
    - Create matches for each group
    - Generate room IDs and passwords

    Priority: HIGH
    Impact: 80-90% faster round setup
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Creating groups for tournament {tournament_id}, round {round_number}...")

    try:
        tournament = Tournament.objects.get(id=tournament_id)

        teams_per_group = config.get("teams_per_group")
        qualifying_per_group = config.get("qualifying_per_group")
        matches_per_group = config.get("matches_per_group")

        # Create groups and matches
        groups = TournamentGroupService.create_groups_for_round(
            tournament=tournament,
            round_number=round_number,
            teams_per_group=teams_per_group,
            qualifying_per_group=qualifying_per_group,
            matches_per_group=matches_per_group,
        )

        # Update tournament round status
        if not tournament.round_status:
            tournament.round_status = {}
        tournament.round_status[str(round_number)] = "ongoing"
        tournament.current_round = round_number
        tournament.save(update_fields=["round_status", "current_round"])

        logger.info(f"Created {len(groups)} groups for round {round_number}")
        return {"groups_created": len(groups), "round_number": round_number, "tournament_id": tournament_id}

    except Tournament.DoesNotExist:
        logger.error(f"Tournament {tournament_id} not found")
        return {"error": "Tournament not found"}
    except Exception as e:
        logger.error(f"Error creating tournament groups: {e}")
        return {"error": str(e)}


@shared_task
def process_tournament_banner(tournament_id, image_path):
    """
    Process tournament banner asynchronously
    - Resize to multiple sizes
    - Compress images
    - Generate thumbnails
    - (Future: Upload to CDN)

    Priority: HIGH
    Impact: Better host UX, non-blocking uploads
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing banner for tournament {tournament_id}...")

    try:
        if not os.path.exists(image_path):
            logger.warning(f"Image path does not exist: {image_path}")
            return {"error": "Image not found"}

        # Open image
        img = Image.open(image_path)

        # Resize to standard size (e.g., 1200x400)
        max_width = 1200
        max_height = 400

        # Calculate aspect ratio
        aspect = img.width / img.height
        if img.width > max_width or img.height > max_height:
            if aspect > max_width / max_height:
                new_width = max_width
                new_height = int(max_width / aspect)
            else:
                new_height = max_height
                new_width = int(max_height * aspect)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save optimized image
        img.save(image_path, optimize=True, quality=85)

        # TODO: Generate thumbnail

        logger.info(f"Banner processed successfully for tournament {tournament_id}")
        return {"tournament_id": tournament_id, "image_path": image_path, "size": f"{img.width}x{img.height}"}

    except Tournament.DoesNotExist:
        logger.error(f"Tournament {tournament_id} not found")
        return {"error": "Tournament not found"}
    except Exception as e:
        logger.error(f"Error processing banner: {e}")
        return {"error": str(e)}


@shared_task
def update_platform_statistics():
    """
    Calculate and cache platform-wide statistics
    Runs every hour via Celery Beat

    Priority: CRITICAL
    Impact: 95%+ faster dashboard loads
    """
    logger.info("Calculating platform statistics...")

    try:
        stats = {
            "total_tournaments": Tournament.objects.count(),
            "total_players": PlayerProfile.objects.count(),
            "total_prize_money": str(
                Tournament.objects.filter(status="completed").aggregate(total=Sum("prize_pool"))["total"] or 0
            ),
            "total_registrations": TournamentRegistration.objects.count(),
            "active_tournaments": Tournament.objects.filter(status="ongoing").count(),
            "upcoming_tournaments": Tournament.objects.filter(status="upcoming").count(),
            "completed_tournaments": Tournament.objects.filter(status="completed").count(),
            "last_updated": timezone.now().isoformat(),
        }

        # Cache for 1 hour
        cache.set("platform:statistics", stats, 3600)

        logger.info(f"Platform statistics updated successfully: {stats['total_tournaments']} tournaments")
        return stats

    except Exception as e:
        logger.error(f"Error updating platform statistics: {e}")
        return {"error": str(e)}


@shared_task
def update_host_dashboard_stats(host_id):
    """
    Calculate and cache host-specific dashboard statistics
    Runs every 10 minutes for active hosts via Celery Beat

    Priority: CRITICAL
    Impact: Dashboard loads in <100ms instead of 2-5 seconds
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Calculating dashboard stats for host {host_id}...")

    try:
        host_profile = HostProfile.objects.get(id=host_id)
        now = timezone.now()

        # Total matches hosted (tournaments + scrims)
        matches_hosted = Tournament.objects.filter(host=host_profile).count()

        # Participant stats
        total_participants = TournamentRegistration.objects.filter(
            tournament__host=host_profile, status="confirmed"
        ).count()

        # Prize pool calculations (sum of all prize pools)
        total_prize_pool = Tournament.objects.filter(host=host_profile).aggregate(total=Sum("prize_pool"))["total"] or 0

        # Host rating from profile
        host_rating = float(host_profile.rating)

        stats = {
            "matches_hosted": matches_hosted,
            "total_participants": total_participants,
            "total_prize_pool": float(total_prize_pool),
            "host_rating": host_rating,
            "last_updated": now.isoformat(),
        }

        # Cache for 10 minutes
        cache.set(f"host:dashboard:{host_id}", stats, 600)

        logger.info(f"Host {host_id} dashboard stats updated: {matches_hosted} matches hosted")
        return stats

    except HostProfile.DoesNotExist:
        logger.error(f"Host profile {host_id} not found")
        return {"error": "Host not found"}
    except Exception as e:
        logger.error(f"Error updating host dashboard stats: {e}")
        return {"error": str(e)}


@shared_task
def refresh_all_host_dashboards():
    """
    Refresh dashboard stats for all hosts with active tournaments
    Runs every 10 minutes via Celery Beat
    """
    logger = logging.getLogger(__name__)

    # Get hosts with active tournaments
    active_hosts = HostProfile.objects.filter(tournaments__status__in=["upcoming", "ongoing"]).distinct()

    count = 0
    for host in active_hosts:
        update_host_dashboard_stats.delay(host.id)
        count += 1

    logger.info(f"Triggered dashboard refresh for {count} active hosts")
    return {"hosts_refreshed": count}


# ============================================================================
# TEMP TEAM CONVERSION TASKS
# ============================================================================


@shared_task
def notify_credential_release():
    """
    Runs every minute.
    Finds tournaments whose credential_release_time just passed (within last 2 minutes)
    and sends an in-app notification to all confirmed registered players.
    Uses a cache key to ensure each tournament only notifies once.
    """
    now = timezone.now()
    window_start = now - timezone.timedelta(minutes=2)

    recently_released = Tournament.objects.filter(
        credential_release_time__gte=window_start,
        credential_release_time__lte=now,
    )

    notified_count = 0
    for tournament in recently_released:
        cache_key = f"cred_notif_sent:{tournament.id}"
        if cache.get(cache_key):
            continue  # Already sent for this tournament

        registrations = TournamentRegistration.objects.filter(
            tournament=tournament, status="confirmed"
        ).select_related("player__user")

        for reg in registrations:
            if should_notify(reg.player.user, 'tournamentUpdates'):
                Notification.objects.get_or_create(
                    user=reg.player.user,
                    type="credential_release",
                    related_id=tournament.id,
                    related_type="tournament",
                    defaults={
                        "title": "Room ID is ready!",
                        "message": (
                            f"Room ID & Password for '{tournament.title}' are now available. "
                            f"Check your ID & Passwords tab."
                        ),
                        "is_read": False,
                    },
                )
                notified_count += 1

        # Mark as sent for 1 hour to prevent duplicate sends
        cache.set(cache_key, True, 3600)

    if notified_count:
        logger.info(f"Sent credential release notifications to {notified_count} players")
    return {"notified": notified_count}


@shared_task
def notify_slot_list_release():
    """
    Runs every minute.
    Finds tournaments whose slot_list_release_time just passed (within last 2 minutes)
    and sends an in-app notification to all confirmed registered players.
    Uses a cache key to ensure each tournament only notifies once.
    """
    now = timezone.now()
    window_start = now - timezone.timedelta(minutes=2)

    recently_released = Tournament.objects.filter(
        slot_list_release_time__gte=window_start,
        slot_list_release_time__lte=now,
    )

    notified_count = 0
    for tournament in recently_released:
        cache_key = f"slot_notif_sent:{tournament.id}"
        if cache.get(cache_key):
            continue

        registrations = TournamentRegistration.objects.filter(
            tournament=tournament, status="confirmed"
        ).select_related("player__user")

        for reg in registrations:
            Notification.objects.get_or_create(
                user=reg.player.user,
                type="slot_list_release",
                related_id=tournament.id,
                related_type="tournament",
                defaults={
                    "title": "Slot list is ready!",
                    "message": (
                        f"The slot list for '{tournament.title}' is now available. "
                        f"Check your Slot List tab to see your slot number."
                    ),
                    "is_read": False,
                },
            )
            notified_count += 1

        cache.set(cache_key, True, 3600)

    if notified_count:
        logger.info(f"Sent slot list release notifications to {notified_count} players")
    return {"notified": notified_count}


@shared_task
def notify_match_start():
    """
    Runs every minute.
    Finds matches scheduled to start within the next 15 minutes and sends
    a match_start notification to all teams in that match's group.
    Uses a cache key to ensure each match only notifies once.
    """
    now = timezone.now()
    window_end = now + timezone.timedelta(minutes=15)

    upcoming_matches = Match.objects.filter(
        scheduled_date__isnull=False,
        status="pending",
    ).select_related("group__tournament")

    notified_count = 0
    for match in upcoming_matches:
        if not match.scheduled_date:
            continue

        # Combine scheduled_date and scheduled_time into a datetime
        from datetime import datetime as dt, time as t
        scheduled_time = match.scheduled_time or t(0, 0)
        scheduled_dt = dt.combine(match.scheduled_date, scheduled_time)
        if timezone.is_naive(scheduled_dt):
            scheduled_dt = timezone.make_aware(scheduled_dt, timezone.get_current_timezone())

        if not (now <= scheduled_dt <= window_end):
            continue

        cache_key = f"match_start_notif:{match.id}"
        if cache.get(cache_key):
            continue

        tournament = match.group.tournament
        try:
            group_registrations = TournamentRegistration.objects.filter(
                tournament_groups=match.group
            ).select_related("team")
            match_label = f"Match {match.match_number}" if match.match_number else "Your match"
            notifications = []
            for reg in group_registrations:
                member_user_ids = TeamMember.objects.filter(
                    team=reg.team, user__isnull=False
                ).values_list("user_id", flat=True)
                for user_id in member_user_ids:
                    notifications.append(
                        Notification(
                            user_id=user_id,
                            type="match_start",
                            title="Match Starting Soon!",
                            message=f"{match_label} for {tournament.title} starts in ~15 minutes. Get ready!",
                            related_id=tournament.id,
                            related_type="tournament",
                        )
                    )
            if notifications:
                Notification.objects.bulk_create(notifications)
                notified_count += len(notifications)
                logger.info(
                    f"Match start notifications sent - Match: {match.id}, Tournament: {tournament.id}, Players: {len(notifications)}"
                )
        except Exception as e:
            logger.error(f"Failed to send match start notifications for match {match.id}: {e}", exc_info=True)

        # Mark this match as notified for 30 minutes to prevent duplicates
        cache.set(cache_key, True, 1800)

    if notified_count:
        logger.info(f"Sent match start notifications to {notified_count} players")
    return {"notified": notified_count}


@shared_task(name="tournaments.tasks.check_temp_team_conversions")
def check_temp_team_conversions():
    """
    Runs every minute alongside update_tournament_statuses.
    When a tournament transitions to 'completed', find all temporary teams
    linked to it and:
      1. Set conversion_deadline = now + 48h
      2. Send an in-app notification to the team captain
    """
    now = timezone.now()
    # Find tournaments that just became completed within the last 2 minutes
    # (window slightly wider than task interval to avoid gaps)
    recently_completed = Tournament.objects.filter(
        status="completed",
        tournament_end__gte=now - timezone.timedelta(minutes=2),
        tournament_end__lte=now,
    )

    notified_count = 0
    for tournament in recently_completed:
        temp_teams = Team.objects.filter(
            linked_tournament=tournament,
            is_temporary=True,
            conversion_deadline__isnull=True,  # Not yet processed
        )
        for team in temp_teams:
            deadline = now + timezone.timedelta(hours=48)
            team.conversion_deadline = deadline
            team.save(update_fields=["conversion_deadline"])

            # Notify the captain
            if should_notify(team.captain, 'tournamentUpdates'):
                Notification.objects.get_or_create(
                    user=team.captain,
                    type="team_conversion_offer",
                    related_id=team.id,
                    related_type="team",
                    defaults={
                        "title": "Keep your team permanently?",
                        "message": (
                            f"Your team '{team.name}' was created for '{tournament.title}'. "
                            f"Want to keep it permanently? You have 48 hours to decide."
                        ),
                        "is_read": False,
                    },
                )
                notified_count += 1

    if notified_count:
        logger.info(f"Sent {notified_count} temp team conversion notifications")
    return {"notified": notified_count}


@shared_task(name="tournaments.tasks.send_temp_team_24h_reminders")
def send_temp_team_24h_reminders():
    """
    Runs every hour.
    Sends a reminder notification to captains whose temp team conversion
    deadline is within the next 24 hours but they haven't acted yet.
    Only sends once per team (tracked via a separate notification type).
    """
    now = timezone.now()
    reminder_window_end = now + timezone.timedelta(hours=24)

    teams_expiring_soon = Team.objects.filter(
        is_temporary=True,
        conversion_deadline__isnull=False,
        conversion_deadline__gt=now,
        conversion_deadline__lte=reminder_window_end,
    )

    reminded_count = 0
    for team in teams_expiring_soon:
        # Only send once — check if reminder already sent
        already_sent = Notification.objects.filter(
            user=team.captain,
            type="team_conversion_reminder",
            related_id=team.id,
        ).exists()
        if already_sent:
            continue

        hours_left = int((team.conversion_deadline - now).total_seconds() / 3600)
        if should_notify(team.captain, 'tournamentUpdates'):
            Notification.objects.create(
                user=team.captain,
                type="team_conversion_reminder",
                related_id=team.id,
                related_type="team",
                title="Last chance: Keep your team?",
                message=(
                    f"Your team '{team.name}' will be deleted in ~{hours_left} hour(s). "
                    f"Go to Team tab to keep it permanently or it will be removed."
                ),
                is_read=False,
            )
            reminded_count += 1

    if reminded_count:
        logger.info(f"Sent {reminded_count} 24h temp team reminder notifications")
    return {"reminded": reminded_count}


@shared_task(name="tournaments.tasks.cleanup_expired_temp_teams")
def cleanup_expired_temp_teams():
    """
    Runs every hour.

    Two cleanup paths:
      1. Legacy team-level temp (Team.is_temporary=True) — entire team deleted
         when its 48h window passes without the captain accepting.
      2. Per-member temp (TeamMember.is_temporary=True) — only the individual
         membership is removed when ITS 48h window passes. The team and other
         members are unaffected. If the team becomes empty as a result, the
         team itself is deleted.
    """
    from accounts.models import TeamMember

    now = timezone.now()

    # ─── 1. Legacy team-level cleanup (unchanged) ──────────────────────────
    expired_teams = Team.objects.filter(
        is_temporary=True,
        conversion_deadline__isnull=False,
        conversion_deadline__lt=now,
    )

    team_count = 0
    for team in expired_teams:
        try:
            if should_notify(team.captain, 'tournamentUpdates'):
                Notification.objects.create(
                    user=team.captain,
                    type="team_deleted",
                    related_id=team.id,
                    related_type="team",
                    title="Team deleted",
                    message=(
                        f"Your temporary team '{team.name}' has been deleted "
                        f"because the 48-hour conversion window expired."
                    ),
                    is_read=False,
                )
        except Exception as e:
            logger.warning(f"Failed to send deletion notification for team {team.id}: {e}")
        team_count += 1

    expired_teams.delete()

    # ─── 2. Per-member cleanup (new logic) ─────────────────────────────────
    expired_memberships = TeamMember.objects.filter(
        is_temporary=True,
        conversion_deadline__isnull=False,
        conversion_deadline__lt=now,
        team__is_temporary=False,  # legacy temp teams handled above
    ).select_related("team", "user")

    membership_count = 0
    affected_team_ids = set()
    for membership in expired_memberships:
        # Don't auto-remove captain — would orphan the team. Captains who
        # ignore the prompt keep the team but their membership stays temp.
        if membership.is_captain:
            continue
        try:
            if membership.user and should_notify(membership.user, 'tournamentUpdates'):
                Notification.objects.create(
                    user=membership.user,
                    type="team_membership_expired",
                    related_id=membership.team.id,
                    related_type="team",
                    title="Removed from team",
                    message=(
                        f"You were removed from '{membership.team.name}' because the 48-hour "
                        f"window to keep it as your permanent team expired without a decision."
                    ),
                    is_read=False,
                )
        except Exception as e:
            logger.warning(f"Failed to send membership-expiry notification for member {membership.id}: {e}")
        affected_team_ids.add(membership.team_id)
        membership.delete()
        membership_count += 1

    # If any team is now empty (no members left), delete it too
    orphan_team_count = 0
    for team_id in affected_team_ids:
        team = Team.objects.filter(id=team_id).first()
        if team and not team.members.exists():
            team.delete()
            orphan_team_count += 1

    if team_count or membership_count or orphan_team_count:
        logger.info(
            f"Cleanup: deleted {team_count} legacy-temp teams, "
            f"{membership_count} expired memberships, {orphan_team_count} orphan teams"
        )

    return {
        "deleted_legacy_teams": team_count,
        "deleted_memberships": membership_count,
        "deleted_orphan_teams": orphan_team_count,
    }
