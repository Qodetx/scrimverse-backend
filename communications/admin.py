import logging
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.urls import reverse
from django.http import HttpResponseRedirect

from .models import BroadcastEmail, IssueReport


class ScrollableCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Checkbox list with a Users-page-style search bar and scrollable container."""

    def render(self, name, value, attrs=None, renderer=None):
        inner_html = super().render(name, value, attrs, renderer)
        list_id = f"cblist__{name}"
        output = (
            '<div style="width:100%;max-width:800px;">'
            '<div style="display:flex;gap:0;margin-bottom:0;border:1px solid #ccc;">'
            '<input type="text" placeholder="Search..." '
            'style="flex:1;padding:6px 10px;border:none;outline:none;font-size:13px;background:#fff;" '
            'onkeydown="if(event.key===\'Enter\'){event.preventDefault();event.stopPropagation();}" '
            'oninput="var q=this.value.toLowerCase();'
            "document.getElementById('" + list_id + "').querySelectorAll('label')"
            '.forEach(function(el){'
            "el.style.display=el.textContent.toLowerCase().indexOf(q)>=0?'':'none';"
            '});" />'
            '<button type="button" '
            'style="padding:6px 16px;background:#417690;color:#fff;border:none;'
            'font-size:13px;font-weight:bold;cursor:pointer;white-space:nowrap;" '
            "onclick=\"this.previousElementSibling.value='';"
            "document.getElementById('" + list_id + "').querySelectorAll('label')"
            '.forEach(function(el){el.style.display=\'\';});">Clear</button>'
            '</div>'
            '<div id="' + list_id + '" style="border:1px solid #ccc;border-top:none;height:200px;'
            'overflow-y:auto;padding:8px 12px;background:#fff;">'
            + inner_html +
            '</div>'
            '</div>'
        )
        return mark_safe(output)


class BroadcastEmailForm(forms.ModelForm):
    class Meta:
        model = BroadcastEmail
        fields = "__all__"
        widgets = {
            "selected_tournaments": ScrollableCheckboxSelectMultiple,
            "selected_users": ScrollableCheckboxSelectMultiple,
        }

logger = logging.getLogger(__name__)

# Fields that are locked once an email has been sent
READONLY_AFTER_SEND = (
    "subject",
    "body",
    "recipient_type",
    "tournament_status_filter",
    "status",
    "total_sent",
    "sent_at",
    "error_message",
    "created_by",
    "created_at",
)


@admin.register(BroadcastEmail)
class BroadcastEmailAdmin(admin.ModelAdmin):
    form = BroadcastEmailForm
    change_form_template = "admin/communications/broadcastemail/change_form.html"
    add_form_template = "admin/communications/broadcastemail/change_form.html"
    # ── List view ────────────────────────────────────────────────────────────
    list_display = (
        "subject",
        "recipient_type_display",
        "tournament_status_filter",
        "status_badge",
        "total_sent",
        "created_by",
        "created_at",
        "sent_at",
    )
    list_filter = ("status", "recipient_type", "tournament_status_filter")
    search_fields = ("subject", "body")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    # ── Add / Change form ────────────────────────────────────────────────────
    fieldsets = (
        (
            "Email Content",
            {
                "fields": ("subject", "body"),
            },
        ),
        (
            "Recipients",
            {
                "fields": (
                    "recipient_type",
                    "tournament_status_filter",
                    "selected_tournaments",
                    "selected_users",
                ),
                "description": (
                    "Choose who receives this email. "
                    "For 'Tournament Participants': optionally pick specific tournaments "
                    "using the box below, or leave empty to target all tournaments "
                    "(filtered by Tournament Status Filter). "
                    "For 'Individual Users': use the users box to hand-pick recipients."
                ),
            },
        ),
        (
            "Status & Tracking",
            {
                "fields": ("status", "total_sent", "sent_at", "error_message", "created_by", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # CheckboxSelectMultiple is used via BroadcastEmailForm — no filter_horizontal

    # ── Custom actions ───────────────────────────────────────────────────────
    actions = ["send_now_action"]

    @admin.action(description="Send selected emails now (queues Celery task)")
    def send_now_action(self, request, queryset):
        from .tasks import send_broadcast_email_task

        queued = 0
        skipped = 0
        for broadcast in queryset:
            if broadcast.status == "sent":
                skipped += 1
                continue
            if broadcast.status == "sending":
                skipped += 1
                continue
            send_broadcast_email_task.delay(broadcast.pk)
            queued += 1

        if queued:
            self.message_user(
                request,
                f"{queued} broadcast(s) queued for sending.",
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} broadcast(s) skipped (already sent or currently sending).",
                messages.WARNING,
            )

    # ── Make fields read-only for already-sent broadcasts ────────────────────
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in ("sent", "sending"):
            return READONLY_AFTER_SEND + ("selected_tournaments", "selected_users")
        # Always show tracking fields as read-only on existing objects
        if obj:
            return ("status", "total_sent", "sent_at", "error_message", "created_by", "created_at")
        return ("status", "total_sent", "sent_at", "error_message", "created_at")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        if "_send_now_form" in request.POST:
            from .tasks import send_broadcast_email_task
            send_broadcast_email_task.delay(obj.pk)
            self.message_user(request, "Broadcast saved and queued for sending (queued Celery task).", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:communications_broadcastemail_changelist"))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_send_now_form" in request.POST:
            from .tasks import send_broadcast_email_task
            send_broadcast_email_task.delay(obj.pk)
            self.message_user(request, "Broadcast updated and queued for sending (queued Celery task).", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:communications_broadcastemail_changelist"))
        return super().response_change(request, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if extra_context is None:
            extra_context = {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj and obj.status in ("sent", "sending"):
                extra_context["is_sent"] = True
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        # We always want the send button on the add page
        return super().add_view(request, form_url, extra_context)

    # ── Display helpers ──────────────────────────────────────────────────────
    @admin.display(description="Recipient Type")
    def recipient_type_display(self, obj):
        return obj.get_recipient_type_display()

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "draft": "#888888",
            "sending": "#f0a500",
            "sent": "#28a745",
            "failed": "#dc3545",
        }
        color = colors.get(obj.status, "#888888")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status.upper(),
        )


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'issue_type', 'priority_badge', 'status_badge_issue',
        'reporter_name', 'anonymous', 'created_at',
    ]
    list_filter = ['issue_type', 'priority', 'status', 'anonymous']
    search_fields = ['title', 'description', 'reporter_name', 'reporter_email']
    readonly_fields = ['created_at', 'updated_at', 'submitted_by']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Report Details', {
            'fields': ('issue_type', 'priority', 'title', 'description', 'steps_to_reproduce', 'evidence', 'evidence_preview'),
        }),
        ('Reporter Info', {
            'fields': ('reporter_name', 'reporter_email', 'anonymous', 'submitted_by'),
        }),
        ('Admin', {
            'fields': ('status', 'admin_notes', 'created_at', 'updated_at'),
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'submitted_by', 'evidence_preview']

    @admin.display(description='Preview')
    def evidence_preview(self, obj):
        if not obj.evidence:
            return '-'
        url = obj.evidence.url
        name = obj.evidence.name.lower()
        if any(name.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height:200px;max-width:400px;border:1px solid #ccc;border-radius:4px;" />'
                '</a>',
                url, url,
            )
        return format_html('<a href="{}" target="_blank">📎 View / Download file</a>', url)

    @admin.display(description='Priority')
    def priority_badge(self, obj):
        colors = {'low': '#28a745', 'medium': '#f0a500', 'high': '#dc3545', 'critical': '#8b0000'}
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(obj.priority, '#888888'),
            obj.priority.upper(),
        )

    @admin.display(description='Status')
    def status_badge_issue(self, obj):
        colors = {
            'open': '#417690',
            'in_progress': '#f0a500',
            'resolved': '#28a745',
            'closed': '#888888',
        }
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(obj.status, '#888888'),
            obj.get_status_display(),
        )
