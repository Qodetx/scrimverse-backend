# Re-export all tasks so existing imports remain unchanged.

from tournaments.tasks.tournament_tasks import (  # noqa: F401
    update_tournament_statuses,
    cleanup_unpaid_tournaments_and_registrations,
    process_tournament_registration,
    create_tournament_groups,
    process_tournament_banner,
    update_platform_statistics,
    update_host_dashboard_stats,
    refresh_all_host_dashboards,
)

from tournaments.tasks.score_tasks import (  # noqa: F401
    update_leaderboard,
    process_round_scores,
    process_match_scores,
)

from tournaments.tasks.email_tasks import (  # noqa: F401
    send_team_invite_emails_task,
    send_tournament_reminders_24h,
    send_tournament_reminders_1h,
    send_tournament_registration_email_task,
    send_player_tournament_reminder_email_task,
    send_host_approved_email_task,
    send_tournament_created_email_task,
    send_tournament_reminder_email_task,
    send_registration_limit_reached_email_task,
    send_max_participants_email_task,
    send_tournament_completed_email_task,
)
