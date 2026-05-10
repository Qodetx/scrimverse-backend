import csv

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html

from .models import CommunityJoin, CommunitySettings


def _build_csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


def _platform_filter(platform):
    """Return list of community_type values matching the platform filter."""
    if platform == "whatsapp":
        return [CommunityJoin.WHATSAPP]
    if platform == "instagram":
        return [CommunityJoin.INSTAGRAM]
    return [CommunityJoin.WHATSAPP, CommunityJoin.INSTAGRAM]


def _export_joiners_csv(platform):
    """Export all users who clicked any of the platform's community button(s)."""
    types = _platform_filter(platform)
    qs = (
        CommunityJoin.objects.filter(community_type__in=types)
        .select_related("user")
        .order_by("-joined_at")
    )
    rows = [
        [
            j.user.username,
            j.user.email,
            j.user.phone_number or "",
            j.get_community_type_display(),
            j.joined_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for j in qs
    ]
    return _build_csv_response(
        f"community_joiners_{platform}.csv",
        ["Username", "Email", "Phone Number", "Platform", "Joined At"],
        rows,
    )


def _export_non_joiners_csv(platform):
    """Export registered tournament players who have NOT clicked the given community button(s).

    For "all", returns users who haven't joined EITHER platform.
    """
    from accounts.models import User
    from tournaments.models import TournamentRegistration

    types = _platform_filter(platform)
    registered_user_ids = (
        TournamentRegistration.objects.filter(status="confirmed")
        .values_list("player__user_id", flat=True)
        .distinct()
    )
    # User is excluded only if they've joined ALL the selected platforms
    if platform == "all":
        joined_wa = set(
            CommunityJoin.objects.filter(community_type=CommunityJoin.WHATSAPP)
            .values_list("user_id", flat=True)
        )
        joined_ig = set(
            CommunityJoin.objects.filter(community_type=CommunityJoin.INSTAGRAM)
            .values_list("user_id", flat=True)
        )
        # Non-joiners of "all" = haven't joined either
        excluded = joined_wa & joined_ig
    else:
        excluded = set(
            CommunityJoin.objects.filter(community_type__in=types)
            .values_list("user_id", flat=True)
        )

    non_joiners = (
        User.objects.filter(id__in=registered_user_ids)
        .exclude(id__in=excluded)
        .order_by("username")
    )
    rows = []
    for user in non_joiners:
        tournament_count = TournamentRegistration.objects.filter(
            player__user=user, status="confirmed"
        ).count()
        rows.append([
            user.username,
            user.email,
            user.phone_number or "",
            tournament_count,
        ])
    return _build_csv_response(
        f"community_non_joiners_{platform}.csv",
        ["Username", "Email", "Phone Number", "Confirmed Tournaments"],
        rows,
    )


@admin.register(CommunitySettings)
class CommunitySettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            "Community Links",
            {
                "fields": ("whatsapp_link", "instagram_link"),
                "description": (
                    "Set the WhatsApp and Instagram community links that appear on the "
                    "Registration Confirmed screen and in the player dashboard. "
                    "Leave a field blank to hide that button from players."
                ),
            },
        ),
        (
            "Info",
            {"fields": ("updated_at",), "classes": ("collapse",)},
        ),
    ]
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not CommunitySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Redirect directly to the single edit page
        obj = CommunitySettings.load()
        from django.shortcuts import redirect
        return redirect(f"/admin/community/communitysettings/{obj.pk}/change/")


@admin.register(CommunityJoin)
class CommunityJoinAdmin(admin.ModelAdmin):
    list_display = ("user_username", "user_email", "user_phone", "community_type_badge", "joined_at")
    list_filter = ("community_type", "joined_at")
    search_fields = ("user__username", "user__email", "user__phone_number")
    readonly_fields = ("user", "community_type", "joined_at")
    ordering = ["-joined_at"]
    change_list_template = "admin/community/communityjoin/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "export-csv/",
                self.admin_site.admin_view(self.export_csv_view),
                name="community_communityjoin_export_csv",
            ),
        ]
        return custom + urls

    def export_csv_view(self, request):
        # Single dropdown with 4 options:
        #   non_joiners  — registered players who haven't joined any community
        #   whatsapp     — users who clicked WhatsApp
        #   instagram    — users who clicked Instagram
        #   all_joiners  — users who clicked either WhatsApp or Instagram
        export_type = request.GET.get("type", "")
        if export_type == "non_joiners":
            return _export_non_joiners_csv("all")
        if export_type == "whatsapp":
            return _export_joiners_csv("whatsapp")
        if export_type == "instagram":
            return _export_joiners_csv("instagram")
        if export_type == "all_joiners":
            return _export_joiners_csv("all")
        return HttpResponse("Invalid export type", status=400)

    def has_add_permission(self, request):
        return False

    def user_username(self, obj):
        return obj.user.username
    user_username.short_description = "Username"
    user_username.admin_order_field = "user__username"

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    def user_phone(self, obj):
        return obj.user.phone_number or "—"
    user_phone.short_description = "Phone"

    def community_type_badge(self, obj):
        if obj.community_type == CommunityJoin.WHATSAPP:
            color = "#25d366"
            label = "WhatsApp"
        else:
            color = "#e1306c"
            label = "Instagram"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            color,
            label,
        )
    community_type_badge.short_description = "Platform"

    def changelist_view(self, request, extra_context=None):
        from accounts.models import User
        from tournaments.models import TournamentRegistration

        registered_count = (
            TournamentRegistration.objects.filter(status="confirmed")
            .values_list("player__user_id", flat=True)
            .distinct()
            .count()
        )
        joined_wa_count = CommunityJoin.objects.filter(
            community_type=CommunityJoin.WHATSAPP
        ).count()
        non_joiner_count = max(0, registered_count - joined_wa_count)

        extra_context = extra_context or {}
        extra_context["non_joiner_count"] = non_joiner_count
        extra_context["registered_count"] = registered_count
        extra_context["joined_wa_count"] = joined_wa_count
        return super().changelist_view(request, extra_context=extra_context)
