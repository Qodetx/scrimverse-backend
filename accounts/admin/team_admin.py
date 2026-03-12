"""
Team admin classes: Team, TeamStatistics, TeamJoinRequest.
TeamMemberInline is defined here alongside TeamAdmin which uses it.
"""
import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html

from accounts.models import Team, TeamJoinRequest, TeamMember, TeamStatistics


# Inline admin for team members
class TeamMemberInline(admin.TabularInline):
    """Inline editor for team members"""

    model = TeamMember
    extra = 0
    fields = ["username", "user", "is_captain"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Enhanced Team Admin with inline members"""

    list_display = [
        "name",
        "captain_display",
        "member_count",
        "matches_display",
        "wins_display",
        "win_rate_display",
        "is_temporary",
    ]
    list_filter = ["is_temporary", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["name", "captain__username", "description"]

    inlines = [TeamMemberInline]

    readonly_fields = ["win_rate", "created_at"]

    actions = ["delete_temporary_teams", "export_teams_csv"]

    def captain_display(self, obj):
        """Display captain with link"""
        return format_html(
            '<a href="/admin/accounts/user/{}/change/">{}</a>',
            obj.captain.id,
            obj.captain.username,
        )

    captain_display.short_description = "Captain"

    def member_count(self, obj):
        """Show number of members"""
        count = obj.members.count()
        return format_html(
            '<span style="font-weight: bold;">{} members</span>',
            count,
        )

    member_count.short_description = "Members"

    def matches_display(self, obj):
        """Display total matches"""
        return format_html(
            '<span style="color: #007bff; font-weight: bold;">{}</span>',
            obj.total_matches,
        )

    matches_display.short_description = "Matches"

    def wins_display(self, obj):
        """Display wins"""
        color = "#28a745" if obj.wins > 0 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.wins,
        )

    wins_display.short_description = "Wins"

    def win_rate_display(self, obj):
        """Display win rate with color"""
        win_rate = obj.win_rate
        color = "#28a745" if win_rate >= 50 else "#ffc107" if win_rate >= 25 else "#dc3545"
        win_rate_str = f"{win_rate:.1f}%"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            win_rate_str,
        )

    win_rate_display.short_description = "Win Rate"

    def delete_temporary_teams(self, request, queryset):
        """Delete temporary teams"""
        temp_teams = queryset.filter(is_temporary=True)
        count = temp_teams.count()
        temp_teams.delete()
        self.message_user(request, f"Deleted {count} temporary team(s).")

    delete_temporary_teams.short_description = "Delete Temporary Teams"

    def export_teams_csv(self, request, queryset):
        """Export teams to CSV"""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="teams.csv"'

        writer = csv.writer(response)
        writer.writerow(["Name", "Captain", "Members", "Matches", "Wins", "Win Rate", "Temporary"])

        for team in queryset:
            writer.writerow(
                [
                    team.name,
                    team.captain.username,
                    team.members.count(),
                    team.total_matches,
                    team.wins,
                    f"{team.win_rate:.1f}%",
                    "Yes" if team.is_temporary else "No",
                ]
            )

        self.message_user(request, f"{queryset.count()} team(s) exported to CSV.")
        return response

    export_teams_csv.short_description = "Export to CSV"


@admin.register(TeamStatistics)
class TeamStatisticsAdmin(admin.ModelAdmin):
    """Enhanced Team Statistics Admin"""

    list_display = ["team", "game_name", "rank_display", "total_points_display", "tournament_stats", "scrim_stats"]
    list_filter = ["game_name", ("team__created_at", admin.DateFieldListFilter)]
    search_fields = ["team__name"]
    ordering = ["rank"]

    readonly_fields = [
        "total_position_points",
        "total_kill_points",
        "total_points",
        "rank",
        "tournament_rank",
        "scrim_rank",
    ]

    def rank_display(self, obj):
        """Display rank with medal"""
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(obj.rank, "")
        color = "#ffc107" if obj.rank <= 3 else "#6c757d"
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 16px;">{} #{}</span>',
            color,
            medal,
            obj.rank,
        )

    rank_display.short_description = "Rank"

    def total_points_display(self, obj):
        """Display total points"""
        return format_html(
            '<span style="color: #28a745; font-weight: bold; font-size: 14px;">{}</span>',
            obj.total_points,
        )

    total_points_display.short_description = "Total Points"

    def tournament_stats(self, obj):
        """Display tournament statistics"""
        return format_html(
            '<div style="font-size: 11px;">'
            "<strong>Wins:</strong> {} | <strong>Points:</strong> {} | <strong>Rank:</strong> #{}"
            "</div>",
            obj.tournament_wins,
            obj.tournament_position_points + obj.tournament_kill_points,
            obj.tournament_rank,
        )

    tournament_stats.short_description = "Tournament Stats"

    def scrim_stats(self, obj):
        """Display scrim statistics"""
        return format_html(
            '<div style="font-size: 11px;">'
            "<strong>Wins:</strong> {} | <strong>Points:</strong> {} | <strong>Rank:</strong> #{}"
            "</div>",
            obj.scrim_wins,
            obj.scrim_position_points + obj.scrim_kill_points,
            obj.scrim_rank,
        )

    scrim_stats.short_description = "Scrim Stats"


@admin.register(TeamJoinRequest)
class TeamJoinRequestAdmin(admin.ModelAdmin):
    """Enhanced Team Join Request Admin"""

    list_display = ["team", "player_display", "request_type_badge", "status_badge", "created_at"]
    list_filter = ["status", "request_type", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["team__name", "player__user__username"]

    actions = ["approve_requests", "reject_requests"]

    def player_display(self, obj):
        """Display player with link"""
        try:
            if not obj.player:
                return "N/A"

            # Check if player has user attribute, if not it might be a user itself
            user = getattr(obj.player, "user", obj.player)
            username = getattr(user, "username", "Unknown")

            return format_html(
                '<a href="/admin/accounts/playerprofile/{}/change/">{}</a>',
                obj.player.id if hasattr(obj.player, "id") else 0,
                username,
            )
        except Exception:
            return "Error Loading User"

    player_display.short_description = "Player"

    def request_type_badge(self, obj):
        """Display request type with color"""
        colors = {
            "request": "#007bff",
            "invite": "#28a745",
        }
        color = colors.get(obj.request_type, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.request_type.upper(),
        )

    request_type_badge.short_description = "Type"

    def status_badge(self, obj):
        """Display status with color"""
        colors = {
            "pending": "#ffc107",
            "accepted": "#28a745",
            "rejected": "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def approve_requests(self, request, queryset):
        """Approve selected requests"""
        updated = queryset.update(status="accepted")
        self.message_user(request, f"{updated} request(s) approved.")

    approve_requests.short_description = "Approve Requests"

    def reject_requests(self, request, queryset):
        """Reject selected requests"""
        updated = queryset.update(status="rejected")
        self.message_user(request, f"{updated} request(s) rejected.")

    reject_requests.short_description = "Reject Requests"
