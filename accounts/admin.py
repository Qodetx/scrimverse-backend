from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import HostProfile, PlayerProfile, Team, TeamJoinRequest, TeamMember, TeamStatistics, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced User Admin"""

    list_display = ["email", "username", "user_type_badge", "is_active", "is_staff", "created_at"]
    list_filter = ["user_type", "is_staff", "is_active", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["email", "username", "phone_number"]
    ordering = ["-created_at"]

    actions = ["activate_users", "deactivate_users", "export_users_csv"]

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Custom Fields",
            {
                "fields": (
                    "user_type",
                    "phone_number",
                    "profile_picture",
                    "username_change_count",
                    "last_username_change",
                )
            },
        ),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Custom Fields", {"fields": ("email", "user_type", "phone_number")}),
    )

    def user_type_badge(self, obj):
        """Display user type with color coding"""
        colors = {
            "player": "#007bff",
            "host": "#28a745",
            "admin": "#dc3545",
        }
        color = colors.get(obj.user_type, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.user_type.upper(),
        )

    user_type_badge.short_description = "Type"

    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} user(s) activated.")

    activate_users.short_description = "Activate Users"

    def deactivate_users(self, request, queryset):
        """Deactivate selected users (ban)"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} user(s) deactivated.")

    deactivate_users.short_description = "Deactivate Users (Ban)"

    def export_users_csv(self, request, queryset):
        """Export users to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'

        writer = csv.writer(response)
        writer.writerow(["Email", "Username", "Type", "Phone", "Active", "Staff", "Created"])

        for user in queryset:
            writer.writerow(
                [
                    user.email,
                    user.username,
                    user.user_type,
                    user.phone_number or "N/A",
                    "Yes" if user.is_active else "No",
                    "Yes" if user.is_staff else "No",
                    user.created_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} user(s) exported to CSV.")
        return response

    export_users_csv.short_description = "Export to CSV"


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    """Enhanced Player Profile Admin"""

    list_display = ["user_display", "tournaments_participated", "wins_display", "preferred_games_display"]
    search_fields = ["user__username", "user__email", "bio"]
    list_filter = [("user__created_at", admin.DateFieldListFilter)]

    readonly_fields = ["total_tournaments_participated", "total_wins"]

    actions = ["reset_statistics", "export_players_csv"]

    def user_display(self, obj):
        """Display user with link"""
        return format_html(
            '<a href="/admin/accounts/user/{}/change/">{}</a>',
            obj.user.id,
            obj.user.username,
        )

    user_display.short_description = "User"

    def tournaments_participated(self, obj):
        """Display tournaments participated"""
        return format_html(
            '<span style="font-weight: bold; color: #007bff;">{}</span>',
            obj.total_tournaments_participated,
        )

    tournaments_participated.short_description = "Tournaments"

    def wins_display(self, obj):
        """Display wins with color"""
        color = "#28a745" if obj.total_wins > 0 else "#6c757d"
        return format_html(
            '<span style="font-weight: bold; color: {};">{}</span>',
            color,
            obj.total_wins,
        )

    wins_display.short_description = "Wins"

    def preferred_games_display(self, obj):
        """Display preferred games"""
        if obj.preferred_games:
            return ", ".join(obj.preferred_games[:3])  # Show first 3
        return "-"

    preferred_games_display.short_description = "Games"

    def reset_statistics(self, request, queryset):
        """Reset statistics for selected players"""
        queryset.update(total_tournaments_participated=0, total_wins=0)
        self.message_user(request, f"Reset statistics for {queryset.count()} player(s).")

    reset_statistics.short_description = "Reset Statistics"

    def export_players_csv(self, request, queryset):
        """Export players to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="players.csv"'

        writer = csv.writer(response)
        writer.writerow(["Username", "Email", "Tournaments", "Wins", "Games"])

        for player in queryset:
            writer.writerow(
                [
                    player.user.username,
                    player.user.email,
                    player.total_tournaments_participated,
                    player.total_wins,
                    ", ".join(player.preferred_games) if player.preferred_games else "N/A",
                ]
            )

        self.message_user(request, f"{queryset.count()} player(s) exported to CSV.")
        return response

    export_players_csv.short_description = "Export to CSV"


@admin.register(HostProfile)
class HostProfileAdmin(admin.ModelAdmin):
    """Enhanced Host Profile Admin"""

    list_display = ["user_display", "tournaments_hosted", "rating_display", "verified_badge"]
    list_display_links = ["user_display"]
    list_editable = []  # Removed verified_badge since it's a display method, not a field
    search_fields = ["user__email", "user__username", "bio"]
    list_filter = ["verified", "rating", ("user__created_at", admin.DateFieldListFilter)]

    readonly_fields = ["total_tournaments_hosted", "rating", "total_ratings"]

    actions = ["verify_hosts", "unverify_hosts", "export_hosts_csv"]

    def user_display(self, obj):
        """Display user with link"""
        return format_html(
            '<a href="/admin/accounts/user/{}/change/">{}</a>',
            obj.user.id,
            obj.user.username,
        )

    user_display.short_description = "User"

    def tournaments_hosted(self, obj):
        """Display tournaments hosted"""
        return format_html(
            '<span style="font-weight: bold; color: #007bff;">{}</span>',
            obj.total_tournaments_hosted,
        )

    tournaments_hosted.short_description = "Tournaments"

    def rating_display(self, obj):
        """Display rating with stars"""
        stars = "⭐" * int(obj.rating)
        rating_str = f"{obj.rating:.1f}"
        return format_html(
            '<span style="font-size: 14px;">{} ({})</span>',
            stars,
            rating_str,
        )

    rating_display.short_description = "Rating"

    def verified_badge(self, obj):
        """Display verified status as badge"""
        if obj.verified:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✓ VERIFIED</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 3px 10px; '
                'border-radius: 3px; font-weight: bold;">✗ UNVERIFIED</span>'
            )

    verified_badge.short_description = "Verified"

    def verify_hosts(self, request, queryset):
        """Verify selected hosts"""
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} host(s) verified.")

    verify_hosts.short_description = "Verify Hosts"

    def unverify_hosts(self, request, queryset):
        """Unverify selected hosts"""
        updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} host(s) unverified.")

    unverify_hosts.short_description = "Unverify Hosts"

    def export_hosts_csv(self, request, queryset):
        """Export hosts to CSV"""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="hosts.csv"'

        writer = csv.writer(response)
        writer.writerow(["Username", "Email", "Tournaments", "Rating", "Verified", "Website"])

        for host in queryset:
            writer.writerow(
                [
                    host.user.username,
                    host.user.email,
                    host.total_tournaments_hosted,
                    f"{host.rating:.1f}",
                    "Yes" if host.verified else "No",
                    host.website or "N/A",
                ]
            )

        self.message_user(request, f"{queryset.count()} host(s) exported to CSV.")
        return response

    export_hosts_csv.short_description = "Export to CSV"


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
        import csv

        from django.http import HttpResponse

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

    list_display = ["team", "rank_display", "total_points_display", "tournament_stats", "scrim_stats"]
    list_filter = [("team__created_at", admin.DateFieldListFilter)]
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
        return format_html(
            '<a href="/admin/accounts/playerprofile/{}/change/">{}</a>',
            obj.player.id,
            obj.player.user.username,
        )

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
