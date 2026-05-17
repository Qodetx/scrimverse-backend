"""
Scoring admin classes: Group, Match, MatchScore, RoundScore.
Inline admins (MatchInline, MatchScoreInline) are defined here alongside
the parent ModelAdmins that use them.
"""
from django.contrib import admin
from django.utils.html import format_html

from tournaments.models import Group, Match, MatchScore, RoundScore


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

    list_display = ["group_name", "tournament", "round_number", "team_count", "status_badge", "winner_display", "created_at"]
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

    def winner_display(self, obj):
        """Display group winner"""
        if obj.winner:
            return format_html(
                '<span style="color: #ffc107; font-weight: bold;">🏆 {}</span>',
                obj.winner.team_name or str(obj.winner)
            )
        return format_html('<span style="color: #6c757d;">-</span>')

    winner_display.short_description = "Winner"

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

    list_display = ["__str__", "group", "match_number", "status_badge", "winner_display", "room_info", "match_time"]
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

    def winner_display(self, obj):
        """Display match winner"""
        if obj.winner:
            return format_html(
                '<span style="color: #ffc107; font-weight: bold;">🏆 {}</span>',
                obj.winner.team_name or str(obj.winner)
            )
        return format_html('<span style="color: #6c757d;">-</span>')

    winner_display.short_description = "Winner"

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
