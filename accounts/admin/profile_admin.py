"""
Player and Host profile admin classes.
"""
import csv

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import HostProfile, PlayerProfile
from tournaments.tasks import send_host_approved_email_task


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

    list_display = [
        "user_display",
        "tournaments_hosted",
        "rating_display",
        "verified_badge",
        "verification_status_badge",
    ]
    list_display_links = ["user_display"]
    list_editable = []  # Removed verified_badge since it's a display method, not a field
    search_fields = ["user__email", "user__username", "bio"]
    list_filter = ["verified", "verification_status", "rating", ("user__created_at", admin.DateFieldListFilter)]

    readonly_fields = [
        "total_tournaments_hosted",
        "rating",
        "total_ratings",
        "aadhar_uploaded_at",
        "aadhar_front_preview",
        "aadhar_back_preview",
    ]

    fieldsets = (
        (
            "User Information",
            {
                "fields": ("user", "bio", "website"),
            },
        ),
        (
            "Trust & Statistics",
            {
                "fields": ("total_tournaments_hosted", "rating", "total_ratings", "verified"),
                "description": (
                    "<strong>Verified Badge:</strong> The blue checkmark badge shown on host profiles. "
                    "This is a trust indicator for premium/established hosts and is independent of Aadhar approval."
                ),
            },
        ),
        (
            "Aadhar Verification (Access Control)",
            {
                "fields": (
                    "verification_status",
                    "aadhar_uploaded_at",
                    "aadhar_front_preview",
                    "aadhar_back_preview",
                    "verification_notes",
                ),
                "classes": ("collapse",),
                "description": (
                    "<strong>Verification Status:</strong> Controls whether the host can access their dashboard. "
                    "'Approved' grants access, 'Pending' blocks access, 'Rejected' blocks access. "
                    "This is separate from the verified badge above."
                ),
            },
        ),
    )

    actions = ["verify_hosts", "unverify_hosts", "approve_verification", "reject_verification", "export_hosts_csv"]

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

    def verification_status_badge(self, obj):
        """Display verification status as badge"""
        colors = {
            "pending": "#ffc107",
            "approved": "#28a745",
            "rejected": "#dc3545",
        }
        color = colors.get(obj.verification_status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.verification_status.upper(),
        )

    verification_status_badge.short_description = "Aadhaar Verification Status"

    def aadhar_front_preview(self, obj):
        """Display Aadhar front image previews"""
        if obj.aadhar_card_front:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width: 300px; max-height: 200px; border: 1px solid #ddd; padding: 5px;" />'
                "</a>",
                obj.aadhar_card_front.url,
                obj.aadhar_card_front.url,
            )
        return "No image uploaded"

    aadhar_front_preview.short_description = "Aadhar Card (Front)"

    def aadhar_back_preview(self, obj):
        """Display Aadhar back image preview"""
        if obj.aadhar_card_back:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width: 300px; max-height: 200px; border: 1px solid #ddd; padding: 5px;" />'
                "</a>",
                obj.aadhar_card_back.url,
                obj.aadhar_card_back.url,
            )
        return "No image uploaded"

    aadhar_back_preview.short_description = "Aadhar Card (Back)"

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

    def approve_verification(self, request, queryset):
        """Approve Aadhar verification for selected hosts"""
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        approved_count = 0

        for host_profile in queryset:
            if host_profile.verification_status != "approved":
                host_profile.verification_status = "approved"
                host_profile.save()
                approved_count += 1

                # 📧 SEND HOST APPROVAL EMAIL
                send_host_approved_email_task.delay(
                    user_email=host_profile.user.email,
                    user_name=host_profile.user.username,
                    host_name=host_profile.user.username,
                    approved_at=timezone.now().strftime("%B %d, %Y at %I:%M %p"),
                    host_dashboard_url=f"{frontend_url}/host/dashboard",
                )

        self.message_user(
            request,
            f"✅ {approved_count} host(s) Aadhar verification approved. Approval emails sent. "
            f"Use 'Verify Hosts' to add verified badge separately.",
        )

    approve_verification.short_description = "✓ Approve Aadhar Verification"

    def reject_verification(self, request, queryset):
        """Reject Aadhar verification for selected hosts"""
        updated = queryset.update(verification_status="rejected")
        self.message_user(
            request,
            f"{updated} host(s) Aadhar verification rejected. Please add rejection notes in the host profile.",
        )

    reject_verification.short_description = "✗ Reject Aadhar Verification"

    def export_hosts_csv(self, request, queryset):
        """Export hosts to CSV"""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="hosts.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Username", "Email", "Tournaments", "Rating", "Verified", "Aadhaar Verification Status", "Website"]
        )

        for host in queryset:
            writer.writerow(
                [
                    host.user.username,
                    host.user.email,
                    host.total_tournaments_hosted,
                    f"{host.rating:.1f}",
                    "Yes" if host.verified else "No",
                    host.verification_status,
                    host.website or "N/A",
                ]
            )

        self.message_user(request, f"{queryset.count()} host(s) exported to CSV.")
        return response

    export_hosts_csv.short_description = "Export to CSV"
