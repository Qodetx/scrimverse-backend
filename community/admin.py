import csv

from django.contrib import admin
from django.db.models import Q
from django.http import HttpResponse
from django.utils.html import format_html

from .models import CommunityJoin, CommunitySettings


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


def export_whatsapp_nonjoiner_csv(modeladmin, request, queryset):
    """
    Export CSV of all registered tournament players who have NOT clicked WhatsApp.
    Ignores the queryset selection — always exports the full non-joiner list.
    """
    from accounts.models import User
    from tournaments.models import TournamentRegistration

    # All users with at least one confirmed registration
    registered_user_ids = (
        TournamentRegistration.objects.filter(status="confirmed")
        .values_list("player__user_id", flat=True)
        .distinct()
    )

    # Users who have already joined WhatsApp
    joined_user_ids = CommunityJoin.objects.filter(
        community_type=CommunityJoin.WHATSAPP
    ).values_list("user_id", flat=True)

    # Non-joiners = registered but haven't clicked WhatsApp
    non_joiners = User.objects.filter(
        id__in=registered_user_ids
    ).exclude(
        id__in=joined_user_ids
    ).order_by("username")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="whatsapp_non_joiners.csv"'

    writer = csv.writer(response)
    writer.writerow(["Username", "Email", "Phone Number", "Confirmed Tournaments"])

    for user in non_joiners:
        tournament_count = TournamentRegistration.objects.filter(
            player__user=user, status="confirmed"
        ).count()
        writer.writerow([
            user.username,
            user.email,
            user.phone_number or "",
            tournament_count,
        ])

    return response


export_whatsapp_nonjoiner_csv.short_description = "Export WhatsApp non-joiners as CSV"


@admin.register(CommunityJoin)
class CommunityJoinAdmin(admin.ModelAdmin):
    list_display = ("user_username", "user_email", "user_phone", "community_type_badge", "joined_at")
    list_filter = ("community_type", "joined_at")
    search_fields = ("user__username", "user__email", "user__phone_number")
    readonly_fields = ("user", "community_type", "joined_at")
    actions = [export_whatsapp_nonjoiner_csv]
    ordering = ["-joined_at"]

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
