"""
User and Aadhar Verification admin classes.
"""
import csv

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import HostProfile, User
from tournaments.tasks import send_host_approved_email_task


# Proxy model for Aadhar Verification (for dedicated admin interface)
class AadharVerification(HostProfile):
    """Proxy model for Aadhar card verification management"""

    class Meta:
        proxy = True
        verbose_name = "Aadhar Verification"
        verbose_name_plural = "Aadhar Verifications"


@admin.register(AadharVerification)
class AadharVerificationAdmin(admin.ModelAdmin):
    """Dedicated admin interface for Aadhar card verification"""

    list_display = [
        "host_name",
        "email",
        "phone_number",
        "uploaded_at_display",
        "verification_status_badge",
        "aadhar_preview",
    ]
    list_display_links = ["host_name"]
    list_filter = ["verification_status", ("aadhar_uploaded_at", admin.DateFieldListFilter)]
    search_fields = ["user__username", "user__email", "user__phone_number"]
    ordering = ["-aadhar_uploaded_at"]

    readonly_fields = [
        "user",
        "aadhar_uploaded_at",
        "total_tournaments_hosted",
        "rating",
        "total_ratings",
        "verified",
        "aadhar_front_large_preview",
        "aadhar_back_large_preview",
    ]

    fieldsets = (
        (
            "Host Information",
            {
                "fields": ("user", "total_tournaments_hosted", "rating", "verified"),
            },
        ),
        (
            "Aadhar Card Images",
            {
                "fields": (
                    "aadhar_uploaded_at",
                    "aadhar_front_large_preview",
                    "aadhar_back_large_preview",
                ),
                "description": "Review the Aadhar card images carefully before approving.",
            },
        ),
        (
            "Verification Decision",
            {
                "fields": ("verification_status", "verification_notes"),
                "description": "Approve or reject the verification. Add notes if rejecting.",
            },
        ),
    )

    actions = ["approve_verification", "reject_verification"]

    def get_queryset(self, request):
        """Show only hosts who have uploaded Aadhar cards"""
        qs = super().get_queryset(request)
        return qs.exclude(aadhar_card_front="").exclude(aadhar_card_back="")

    def host_name(self, obj):
        """Display host username"""
        return obj.user.username

    host_name.short_description = "Host Name"
    host_name.admin_order_field = "user__username"

    def email(self, obj):
        """Display host email"""
        return obj.user.email

    email.short_description = "Email"
    email.admin_order_field = "user__email"

    def phone_number(self, obj):
        """Display host phone number"""
        return obj.user.phone_number or "N/A"

    phone_number.short_description = "Phone"

    def uploaded_at_display(self, obj):
        """Display upload timestamp"""
        if obj.aadhar_uploaded_at:
            return obj.aadhar_uploaded_at.strftime("%b %d, %Y %I:%M %p")
        return "Not uploaded"

    uploaded_at_display.short_description = "Uploaded At"
    uploaded_at_display.admin_order_field = "aadhar_uploaded_at"

    def verification_status_badge(self, obj):
        """Display verification status as badge"""
        colors = {
            "pending": "#ffc107",
            "approved": "#28a745",
            "rejected": "#dc3545",
        }
        color = colors.get(obj.verification_status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 12px; '
            'border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.verification_status.upper(),
        )

    verification_status_badge.short_description = "Status"

    def aadhar_preview(self, obj):
        """Display small preview thumbnails"""
        if obj.aadhar_card_front and obj.aadhar_card_back:
            return format_html(
                '<div style="display: flex; gap: 5px;">'
                '<img src="{}" style="width: 60px; height: 40px; object-fit: cover; border: 1px solid #ddd;" title="Front"/>'  # noqa: E501
                '<img src="{}" style="width: 60px; height: 40px; object-fit: cover; border: 1px solid #ddd;" title="Back"/>'  # noqa: E501
                "</div>",
                obj.aadhar_card_front.url,
                obj.aadhar_card_back.url,
            )
        return "No images"

    aadhar_preview.short_description = "Preview"

    def aadhar_front_large_preview(self, obj):
        """Display large Aadhar front image preview"""
        if obj.aadhar_card_front:
            return format_html(
                '<div style="margin: 10px 0;">'
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width: 600px; max-height: 400px; border: 2px solid #ddd; '
                'padding: 10px; background: #f9f9f9; border-radius: 8px; cursor: pointer;" />'
                "</a>"
                '<p style="margin-top: 5px; color: #666; font-size: 12px;">Click image to view full size in new tab</p>'
                "</div>",
                obj.aadhar_card_front.url,
                obj.aadhar_card_front.url,
            )
        return format_html('<p style="color: #dc3545;">No front image uploaded</p>')

    aadhar_front_large_preview.short_description = "Aadhar Card - Front Side"

    def aadhar_back_large_preview(self, obj):
        """Display large Aadhar back image preview"""
        if obj.aadhar_card_back:
            return format_html(
                '<div style="margin: 10px 0;">'
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width: 600px; max-height: 400px; border: 2px solid #ddd; '
                'padding: 10px; background: #f9f9f9; border-radius: 8px; cursor: pointer;" />'
                "</a>"
                '<p style="margin-top: 5px; color: #666; font-size: 12px;">Click image to view full size in new tab</p>'
                "</div>",
                obj.aadhar_card_back.url,
                obj.aadhar_card_back.url,
            )
        return format_html('<p style="color: #dc3545;">No back image uploaded</p>')

    aadhar_back_large_preview.short_description = "Aadhar Card - Back Side"

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
            f"✅ Successfully approved {approved_count} host(s). They can now access their dashboard. "
            f"Approval emails have been sent. Note: Use 'Verify Hosts' action separately to give them the verified badge.",  # noqa: E501
            level="success",
        )

    approve_verification.short_description = "✅ Approve Selected Verifications"

    def reject_verification(self, request, queryset):
        """Reject Aadhar verification for selected hosts"""
        updated = queryset.update(verification_status="rejected")
        self.message_user(
            request,
            f"❌ Rejected {updated} host(s). Please add rejection notes in each host's detail page.",
            level="warning",
        )

    reject_verification.short_description = "❌ Reject Selected Verifications"

    def has_add_permission(self, request):
        """Disable add functionality (this is for verification only)"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable delete functionality (use Host Profiles for that)"""
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced User Admin"""

    list_display = [
        "email",
        "username",
        "user_type_badge",
        "email_verified_badge",
        "is_active",
        "is_staff",
        "created_at",
    ]
    list_filter = [
        "user_type",
        "is_email_verified",
        "is_staff",
        "is_active",
        (("created_at", admin.DateFieldListFilter)),
    ]
    search_fields = ["email", "username", "phone_number"]
    ordering = ["-created_at"]

    actions = ["activate_users", "deactivate_users", "verify_emails", "export_users_csv"]

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Custom Fields",
            {
                "fields": (
                    "user_type",
                    "phone_number",
                    "profile_picture",
                    "is_email_verified",
                    "email_verification_token",
                    "email_verification_sent_at",
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

    def email_verified_badge(self, obj):
        """Display email verification status as icon"""
        return obj.is_email_verified

    email_verified_badge.short_description = "Email Verified"
    email_verified_badge.boolean = True  # This makes Django use the green checkmark / red X icons

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

    def verify_emails(self, request, queryset):
        """Manually verify emails for selected users"""
        updated = queryset.update(is_email_verified=True, is_active=True)
        self.message_user(
            request,
            f"✅ {updated} user(s) email verified and activated. They can now login.",
            level="success",
        )

    verify_emails.short_description = "Verify Emails"

    def export_users_csv(self, request, queryset):
        """Export users to CSV"""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'

        writer = csv.writer(response)
        writer.writerow(["Email", "Username", "Type", "Phone", "Email Verified", "Active", "Staff", "Created"])

        for user in queryset:
            writer.writerow(
                [
                    user.email,
                    user.username,
                    user.user_type,
                    user.phone_number or "N/A",
                    "Yes" if user.is_email_verified else "No",
                    "Yes" if user.is_active else "No",
                    "Yes" if user.is_staff else "No",
                    user.created_at,
                ]
            )

        self.message_user(request, f"{queryset.count()} user(s) exported to CSV.")
        return response

    export_users_csv.short_description = "Export to CSV"
