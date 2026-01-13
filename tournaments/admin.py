from django.contrib import admin
from django.utils.html import format_html

from tournaments.models import Group, HostRating, Match, MatchScore, RoundScore, Tournament, TournamentRegistration


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    """Enhanced Tournament Admin with advanced features"""

    list_display = [
        "title",
        "event_mode_badge",
        "game_name",
        "status_badge",
        "participant_info",
        "revenue_display",
        "host",
        "tournament_start",
        "plan_type",
    ]

    list_filter = [
        "event_mode",
        "status",
        "game_name",
        "game_mode",
        "plan_type",
        "plan_payment_status",
        ("tournament_start", admin.DateFieldListFilter),
        ("tournament_end", admin.DateFieldListFilter),
        "host",
    ]

    search_fields = [
        "title",
        "description",
        "host__user__username",
        "host__user__email",
        "game_name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "participant_info",
        "revenue_display",
        "completion_percentage",
    ]

    fieldsets = [
        (
            "Basic Information",
            {
                "fields": (
                    "title",
                    "description",
                    "host",
                    "event_mode",
                )
            },
        ),
        (
            "Game Settings",
            {
                "fields": (
                    "game_name",
                    "game_mode",
                    "max_participants",
                    "current_participants",
                    "participant_info",
                )
            },
        ),
        (
            "Financial",
            {
                "fields": (
                    "entry_fee",
                    "prize_pool",
                    "revenue_display",
                    "plan_type",
                    "plan_payment_status",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "registration_start",
                    "registration_end",
                    "tournament_start",
                    "tournament_end",
                    "tournament_date",
                    "tournament_time",
                )
            },
        ),
        (
            "Tournament Structure",
            {
                "fields": (
                    "rounds",
                    "use_groups_system",
                    "max_matches",
                ),
                "description": "Configure tournament rounds and match structure",
            },
        ),
        (
            "Status & Progress",
            {
                "fields": (
                    "status",
                    "current_round",
                    "round_status",
                    "selected_teams",
                    "winners",
                    "completion_percentage",
                )
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "rules",
                    "banner_image",
                    "tournament_file",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    ]

    actions = [
        "mark_as_completed",
        "mark_as_ongoing",
        "mark_as_upcoming",
        "mark_as_featured",
        "unmark_as_featured",
        "recalculate_participants",
        "bulk_cancel",
        "export_to_csv",
        "clone_tournament",
    ]

    # Custom display methods
    def event_mode_badge(self, obj):
        """Display event mode with color coding"""
        colors = {
            "TOURNAMENT": "#007bff",  # Blue
            "SCRIM": "#28a745",  # Green
        }
        color = colors.get(obj.event_mode, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.event_mode,
        )

    event_mode_badge.short_description = "Type"

    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            "upcoming": "#ffc107",  # Yellow
            "ongoing": "#28a745",  # Green
            "completed": "#6c757d",  # Gray
            "cancelled": "#dc3545",  # Red
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def participant_info(self, obj):
        """Show participant count with progress bar"""
        percentage = (obj.current_participants / obj.max_participants * 100) if obj.max_participants > 0 else 0
        color = "#28a745" if percentage >= 80 else "#ffc107" if percentage >= 50 else "#dc3545"

        return format_html(
            '<div style="width: 100px;">'
            '<div style="background-color: #e9ecef; border-radius: 3px; overflow: hidden;">'
            '<div style="background-color: {}; width: {}%; height: 20px; text-align: center; '
            'color: white; font-size: 11px; line-height: 20px;">{}/{}</div>'
            "</div></div>",
            color,
            min(percentage, 100),
            obj.current_participants,
            obj.max_participants,
        )

    participant_info.short_description = "Participants"

    def revenue_display(self, obj):
        """Calculate and display total revenue"""
        revenue = obj.entry_fee * obj.current_participants
        color = "#28a745" if revenue > 10000 else "#6c757d"
        revenue_str = f"₹{revenue:,.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            revenue_str,
        )

    revenue_display.short_description = "Revenue"

    def completion_percentage(self, obj):
        """Show tournament completion percentage"""
        if not obj.rounds or obj.status == "upcoming":
            return "0%"

        total_rounds = len(obj.rounds)
        completed_rounds = 0

        if obj.round_status:
            completed_rounds = sum(1 for status in obj.round_status.values() if status == "completed")

        percentage = (completed_rounds / total_rounds * 100) if total_rounds > 0 else 0

        return format_html(
            '<div style="width: 100px;">'
            '<div style="background-color: #e9ecef; border-radius: 3px; overflow: hidden;">'
            '<div style="background-color: #007bff; width: {}%; height: 20px; text-align: center; '
            'color: white; font-size: 11px; line-height: 20px;">{}%</div>'
            "</div></div>",
            min(percentage, 100),
            int(percentage),
        )

    completion_percentage.short_description = "Completion"

    # Custom actions
    def mark_as_completed(self, request, queryset):
        """Mark selected tournaments as completed"""
        updated = queryset.update(status="completed")
        self.message_user(request, f"{updated} tournament(s) marked as completed.")

    mark_as_completed.short_description = "Mark as Completed"

    def mark_as_ongoing(self, request, queryset):
        """Mark selected tournaments as ongoing"""
        updated = queryset.update(status="ongoing")
        self.message_user(request, f"{updated} tournament(s) marked as ongoing.")

    mark_as_ongoing.short_description = "Mark as Ongoing"

    def mark_as_upcoming(self, request, queryset):
        """Mark selected tournaments as upcoming"""
        updated = queryset.update(status="upcoming")
        self.message_user(request, f"{updated} tournament(s) marked as upcoming.")

    mark_as_upcoming.short_description = "Mark as Upcoming"

    def export_to_csv(self, request, queryset):
        """Export selected tournaments to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="tournaments.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Title", "Event Mode", "Game", "Status", "Participants", "Entry Fee", "Prize Pool", "Start Date", "Host"]
        )

        for tournament in queryset:
            writer.writerow(
                [
                    tournament.title,
                    tournament.event_mode,
                    tournament.game_name,
                    tournament.status,
                    f"{tournament.current_participants}/{tournament.max_participants}",
                    tournament.entry_fee,
                    tournament.prize_pool,
                    tournament.tournament_start,
                    tournament.host.user.username,
                ]
            )

        self.message_user(request, f"{queryset.count()} tournament(s) exported to CSV.")
        return response

    export_to_csv.short_description = "Export to CSV"

    def clone_tournament(self, request, queryset):
        """Clone selected tournaments"""
        from datetime import timedelta

        from django.utils import timezone

        cloned_count = 0
        for tournament in queryset:
            # Create a copy
            tournament.pk = None
            tournament.id = None
            tournament.title = f"{tournament.title} (Copy)"
            tournament.current_participants = 0
            tournament.status = "upcoming"
            tournament.current_round = 0
            tournament.round_status = {}
            tournament.selected_teams = {}
            tournament.winners = {}

            # Adjust dates to future
            now = timezone.now()
            tournament.registration_start = now + timedelta(days=7)
            tournament.registration_end = now + timedelta(days=14)
            tournament.tournament_start = now + timedelta(days=15)
            tournament.tournament_end = now + timedelta(days=16)

            tournament.save()
            cloned_count += 1

        self.message_user(request, f"{cloned_count} tournament(s) cloned successfully.")

    clone_tournament.short_description = "Clone Tournament"

    def mark_as_featured(self, request, queryset):
        """Mark selected tournaments as featured"""
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} tournament(s) marked as featured.")

    mark_as_featured.short_description = "Mark as Featured"

    def unmark_as_featured(self, request, queryset):
        """Remove featured status from selected tournaments"""
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} tournament(s) unmarked as featured.")

    unmark_as_featured.short_description = "Remove Featured Status"

    def recalculate_participants(self, request, queryset):
        """Recalculate current_participants count from confirmed registrations"""
        from tournaments.models import TournamentRegistration

        updated_count = 0
        for tournament in queryset:
            actual_count = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()

            if tournament.current_participants != actual_count:
                tournament.current_participants = actual_count
                tournament.save(update_fields=["current_participants"])
                updated_count += 1

        self.message_user(
            request,
            f"Recalculated participants for {updated_count} tournament(s). " f"Total checked: {queryset.count()}",
        )

    recalculate_participants.short_description = "Recalculate Participant Counts"

    def bulk_cancel(self, request, queryset):
        """Cancel selected tournaments"""
        updated = queryset.update(status="cancelled")
        self.message_user(request, f"{updated} tournament(s) cancelled.")

    bulk_cancel.short_description = "Cancel Tournaments"


@admin.register(TournamentRegistration)
class TournamentRegistrationAdmin(admin.ModelAdmin):
    """Enhanced Registration Admin with bulk actions and better display"""

    list_display = [
        "tournament",
        "team_name",
        "player_display",
        "team_display",
        "player_count",
        "status_badge",
        "payment_badge",
        "registered_at",
    ]

    list_filter = [
        "status",
        "payment_status",
        "tournament__event_mode",
        "tournament__game_name",
        ("registered_at", admin.DateFieldListFilter),
        "tournament",
    ]

    search_fields = [
        "team_name",
        "player__user__username",
        "player__user__email",
        "tournament__title",
        "team__name",
    ]

    readonly_fields = ["registered_at", "player_count", "team_members_display"]

    fieldsets = [
        (
            "Registration Info",
            {
                "fields": (
                    "tournament",
                    "player",
                    "team",
                    "team_name",
                    "player_count",
                )
            },
        ),
        (
            "Team Members",
            {
                "fields": (
                    "team_members",
                    "team_members_display",
                ),
                "description": "List of players in this team",
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "payment_status",
                    "registered_at",
                )
            },
        ),
    ]

    actions = [
        "approve_registrations",
        "reject_registrations",
        "mark_payment_confirmed",
        "mark_payment_pending",
        "export_registrations_csv",
    ]

    # Custom display methods
    def player_display(self, obj):
        """Display player with link"""
        if obj.player:
            return format_html(
                '<a href="/admin/accounts/playerprofile/{}/change/">{}</a>',
                obj.player.id,
                obj.player.user.username,
            )
        return "-"

    player_display.short_description = "Player"

    def team_display(self, obj):
        """Display team with link if exists"""
        if obj.team:
            return format_html(
                '<a href="/admin/accounts/team/{}/change/">{}</a>',
                obj.team.id,
                obj.team.name,
            )
        return "-"

    team_display.short_description = "Team"

    def player_count(self, obj):
        """Show number of players in team"""
        count = len(obj.team_members) if obj.team_members else 0
        color = "#28a745" if count >= 4 else "#ffc107" if count >= 2 else "#dc3545"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} players</span>',
            color,
            count,
        )

    player_count.short_description = "Team Size"

    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            "pending": "#ffc107",  # Yellow
            "confirmed": "#28a745",  # Green
            "rejected": "#dc3545",  # Red
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def payment_badge(self, obj):
        """Display payment status with color coding"""
        if obj.payment_status:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">PAID</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">UNPAID</span>'
            )

    payment_badge.short_description = "Payment"

    def team_members_display(self, obj):
        """Display team members in a formatted way"""
        if not obj.team_members:
            return "No team members"

        members_html = "<ul style='margin: 0; padding-left: 20px;'>"
        for member in obj.team_members:
            members_html += f"<li>{member.get('username', 'Unknown')} - {member.get('in_game_name', 'N/A')}</li>"
        members_html += "</ul>"

        return format_html(members_html)

    team_members_display.short_description = "Team Members"

    # Custom actions
    def approve_registrations(self, request, queryset):
        """Approve selected registrations"""
        updated = queryset.update(status="confirmed")
        self.message_user(request, f"{updated} registration(s) approved.")

    approve_registrations.short_description = "Approve Registrations"

    def reject_registrations(self, request, queryset):
        """Reject selected registrations"""
        updated = queryset.update(status="rejected")
        # Decrease participant count for rejected registrations
        for reg in queryset:
            if reg.tournament.current_participants > 0:
                reg.tournament.current_participants -= 1
                reg.tournament.save(update_fields=["current_participants"])

        self.message_user(request, f"{updated} registration(s) rejected.")

    reject_registrations.short_description = "Reject Registrations"

    def mark_payment_confirmed(self, request, queryset):
        """Mark payment as confirmed"""
        updated = queryset.update(payment_status=True)
        self.message_user(request, f"{updated} payment(s) marked as confirmed.")

    mark_payment_confirmed.short_description = "Mark Payment Confirmed"

    def mark_payment_pending(self, request, queryset):
        """Mark payment as pending"""
        updated = queryset.update(payment_status=False)
        self.message_user(request, f"{updated} payment(s) marked as pending.")

    mark_payment_pending.short_description = "Mark Payment Pending"

    def export_registrations_csv(self, request, queryset):
        """Export registrations to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="registrations.csv"'

        writer = csv.writer(response)
        writer.writerow(["Tournament", "Team Name", "Player", "Status", "Payment Status", "Team Size", "Registered At"])

        for reg in queryset:
            writer.writerow(
                [
                    reg.tournament.title,
                    reg.team_name,
                    reg.player.user.username if reg.player else "N/A",
                    reg.status,
                    "Paid" if reg.payment_status else "Unpaid",
                    len(reg.team_members) if reg.team_members else 0,
                    reg.registered_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} registration(s) exported to CSV.")
        return response

    export_registrations_csv.short_description = "Export to CSV"


@admin.register(HostRating)
class HostRatingAdmin(admin.ModelAdmin):
    """Enhanced Host Rating Admin with moderation features"""

    list_display = ["host_display", "player_display", "rating_stars", "tournament_display", "created_at"]
    list_filter = ["rating", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["host__user__username", "player__user__username", "review"]
    readonly_fields = ["created_at"]

    actions = ["delete_selected_ratings", "export_ratings_csv"]

    def host_display(self, obj):
        """Display host with link"""
        return format_html(
            '<a href="/admin/accounts/hostprofile/{}/change/">{}</a>',
            obj.host.id,
            obj.host.user.username,
        )

    host_display.short_description = "Host"

    def player_display(self, obj):
        """Display player with link"""
        return format_html(
            '<a href="/admin/accounts/playerprofile/{}/change/">{}</a>',
            obj.player.id,
            obj.player.user.username,
        )

    player_display.short_description = "Player"

    def rating_stars(self, obj):
        """Display rating as stars"""
        stars = "⭐" * obj.rating
        color = "#ffc107" if obj.rating >= 4 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-size: 16px;">{} ({})</span>',
            color,
            stars,
            obj.rating,
        )

    rating_stars.short_description = "Rating"

    def tournament_display(self, obj):
        """Display tournament if exists"""
        if obj.tournament:
            return format_html(
                '<a href="/admin/tournaments/tournament/{}/change/">{}</a>',
                obj.tournament.id,
                obj.tournament.title,
            )
        return "-"

    tournament_display.short_description = "Tournament"

    def delete_selected_ratings(self, request, queryset):
        """Delete selected ratings (for spam/inappropriate content)"""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"{count} rating(s) deleted.")

    delete_selected_ratings.short_description = "Delete Selected Ratings"

    def export_ratings_csv(self, request, queryset):
        """Export ratings to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="host_ratings.csv"'

        writer = csv.writer(response)
        writer.writerow(["Host", "Player", "Rating", "Review", "Tournament", "Date"])

        for rating in queryset:
            writer.writerow(
                [
                    rating.host.user.username,
                    rating.player.user.username,
                    rating.rating,
                    rating.review,
                    rating.tournament.title if rating.tournament else "N/A",
                    rating.created_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} rating(s) exported to CSV.")
        return response

    export_ratings_csv.short_description = "Export to CSV"


# Inline admins for better editing
class MatchInline(admin.TabularInline):
    """Inline editor for matches within a group"""

    model = Match
    extra = 0
    fields = ["match_number", "match_id", "match_password", "status", "started_at", "ended_at"]
    readonly_fields = ["started_at", "ended_at"]


class MatchScoreInline(admin.TabularInline):
    """Inline editor for match scores"""

    model = MatchScore
    extra = 0
    fields = ["team", "wins", "position_points", "kill_points", "total_points"]
    readonly_fields = ["total_points"]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """Enhanced Group Admin with inline match editing"""

    list_display = ["group_name", "tournament", "round_number", "team_count", "status_badge", "created_at"]
    list_filter = ["status", "round_number", "tournament__event_mode"]
    search_fields = ["group_name", "tournament__title"]
    ordering = ["tournament", "round_number", "group_name"]

    inlines = [MatchInline]

    actions = ["mark_as_completed", "export_groups_csv"]

    def team_count(self, obj):
        """Show number of teams in group"""
        count = obj.teams.count()
        return format_html(
            '<span style="font-weight: bold;">{} teams</span>',
            count,
        )

    team_count.short_description = "Teams"

    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            "waiting": "#ffc107",
            "ongoing": "#28a745",
            "completed": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def mark_as_completed(self, request, queryset):
        """Mark selected groups as completed"""
        updated = queryset.update(status="completed")
        self.message_user(request, f"{updated} group(s) marked as completed.")

    mark_as_completed.short_description = "Mark as Completed"

    def export_groups_csv(self, request, queryset):
        """Export groups to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="groups.csv"'

        writer = csv.writer(response)
        writer.writerow(["Group Name", "Tournament", "Round", "Teams", "Status", "Created"])

        for group in queryset:
            writer.writerow(
                [
                    group.group_name,
                    group.tournament.title,
                    group.round_number,
                    group.teams.count(),
                    group.status,
                    group.created_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} group(s) exported to CSV.")
        return response

    export_groups_csv.short_description = "Export to CSV"


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    """Enhanced Match Admin with inline score editing"""

    list_display = ["__str__", "group", "match_number", "status_badge", "room_info", "match_time"]
    list_filter = ["status", "group__tournament__event_mode"]
    search_fields = ["group__group_name", "match_id", "group__tournament__title"]
    ordering = ["group", "match_number"]

    inlines = [MatchScoreInline]

    fieldsets = [
        (
            "Match Information",
            {"fields": ("group", "match_number", "status")},
        ),
        (
            "Room Credentials",
            {
                "fields": ("match_id", "match_password"),
                "description": "Room ID and password for players to join",
            },
        ),
        (
            "Timing",
            {
                "fields": ("started_at", "ended_at"),
            },
        ),
    ]

    actions = ["mark_as_completed", "generate_room_ids", "export_matches_csv"]

    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            "waiting": "#ffc107",
            "ongoing": "#28a745",
            "completed": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def room_info(self, obj):
        """Display room ID and password"""
        if obj.match_id:
            return format_html(
                "<div><strong>ID:</strong> {}<br><strong>Pass:</strong> {}</div>",
                obj.match_id or "Not set",
                obj.match_password or "Not set",
            )
        return format_html('<span style="color: #dc3545;">Not configured</span>')

    room_info.short_description = "Room Info"

    def match_time(self, obj):
        """Display match timing"""
        if obj.started_at:
            return format_html(
                '<div style="font-size: 11px;"><strong>Started:</strong> {}</div>',
                obj.started_at.strftime("%Y-%m-%d %H:%M"),
            )
        return "-"

    match_time.short_description = "Time"

    def mark_as_completed(self, request, queryset):
        """Mark selected matches as completed"""
        from django.utils import timezone

        updated = 0
        for match in queryset:
            match.status = "completed"
            if not match.ended_at:
                match.ended_at = timezone.now()
            match.save()
            updated += 1

        self.message_user(request, f"{updated} match(es) marked as completed.")

    mark_as_completed.short_description = "Mark as Completed"

    def generate_room_ids(self, request, queryset):
        """Generate random room IDs for matches without them"""
        import random
        import string

        updated = 0
        for match in queryset:
            if not match.match_id:
                match.match_id = "".join(random.choices(string.digits, k=8))
                match.match_password = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
                match.save()
                updated += 1

        self.message_user(request, f"Generated room credentials for {updated} match(es).")

    generate_room_ids.short_description = "Generate Room IDs"

    def export_matches_csv(self, request, queryset):
        """Export matches to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="matches.csv"'

        writer = csv.writer(response)
        writer.writerow(["Tournament", "Group", "Match #", "Room ID", "Password", "Status"])

        for match in queryset:
            writer.writerow(
                [
                    match.group.tournament.title,
                    match.group.group_name,
                    match.match_number,
                    match.match_id or "Not set",
                    match.match_password or "Not set",
                    match.status,
                ]
            )

        self.message_user(request, f"{queryset.count()} match(es) exported to CSV.")
        return response

    export_matches_csv.short_description = "Export to CSV"


@admin.register(MatchScore)
class MatchScoreAdmin(admin.ModelAdmin):
    """Enhanced Match Score Admin"""

    list_display = ["team", "match", "wins", "position_points", "kill_points", "total_points_display"]
    list_filter = ["match__status", "match__group__tournament__event_mode"]
    search_fields = ["team__team_name", "match__group__group_name"]
    ordering = ["-total_points"]

    readonly_fields = ["total_points"]

    def total_points_display(self, obj):
        """Display total points with color"""
        color = "#28a745" if obj.total_points >= 20 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 14px;">{}</span>',
            color,
            obj.total_points,
        )

    total_points_display.short_description = "Total Points"


@admin.register(RoundScore)
class RoundScoreAdmin(admin.ModelAdmin):
    """Enhanced Round Score Admin"""

    list_display = ["team", "tournament", "round_number", "position_points", "kill_points", "total_points_display"]
    list_filter = ["round_number", "tournament__event_mode"]
    search_fields = ["team__team_name", "tournament__title"]
    ordering = ["tournament", "round_number", "-total_points"]

    readonly_fields = ["total_points"]

    actions = ["recalculate_from_matches"]

    def total_points_display(self, obj):
        """Display total points with color"""
        color = "#28a745" if obj.total_points >= 50 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 14px;">{}</span>',
            color,
            obj.total_points,
        )

    total_points_display.short_description = "Total Points"

    def recalculate_from_matches(self, request, queryset):
        """Recalculate round scores from match scores"""
        from django.db.models import Sum

        updated = 0
        for round_score in queryset:
            # Get all match scores for this team in this round
            match_scores = MatchScore.objects.filter(
                team=round_score.team,
                match__group__tournament=round_score.tournament,
                match__group__round_number=round_score.round_number,
            ).aggregate(
                total_pos=Sum("position_points"),
                total_kills=Sum("kill_points"),
            )

            new_pos = match_scores["total_pos"] or 0
            new_kills = match_scores["total_kills"] or 0

            if round_score.position_points != new_pos or round_score.kill_points != new_kills:
                round_score.position_points = new_pos
                round_score.kill_points = new_kills
                round_score.save()
                updated += 1

        self.message_user(request, f"Recalculated {updated} round score(s).")

    recalculate_from_matches.short_description = "Recalculate from Match Scores"
