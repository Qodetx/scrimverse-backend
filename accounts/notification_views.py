"""
Notification API views
GET  /api/accounts/notifications/         — list user's notifications (supports ?limit= and ?offset=)
POST /api/accounts/notifications/mark-all-read/ — mark all as read
PATCH /api/accounts/notifications/<id>/read/ — mark single as read
DELETE /api/accounts/notifications/<id>/ — delete a single notification
POST /api/accounts/notifications/bulk/   — bulk delete or mark-as-read
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Notification, Team

logger = logging.getLogger("accounts")


class NotificationListView(APIView):
    """
    GET /api/accounts/notifications/
    Returns up to 20 recent notifications for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 50)
        offset = int(request.query_params.get("offset", 0))

        qs = Notification.objects.filter(user=request.user)
        total = qs.count()
        notifications = qs[offset:offset + limit]
        data = []
        for n in notifications:
            entry = {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
                "related_id": n.related_id,
                "related_type": n.related_type,
            }
            if n.type == "team_conversion_offer" and n.related_id:
                try:
                    team = Team.objects.get(pk=n.related_id)
                    entry["conversion_deadline"] = (
                        team.conversion_deadline.isoformat()
                        if team.conversion_deadline
                        else None
                    )
                except Team.DoesNotExist:
                    entry["conversion_deadline"] = None
            data.append(entry)
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        logger.debug(
            f"Notifications for {request.user.username}: total={total}, unread={unread_count}, "
            f"offset={offset}, limit={limit}"
        )
        return Response({
            "notifications": data,
            "unread_count": unread_count,
            "total": total,
            "has_more": (offset + limit) < total,
        })


class NotificationMarkReadView(APIView):
    """
    PATCH /api/accounts/notifications/<id>/read/
    Marks a single notification as read.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
            notif.is_read = True
            notif.save(update_fields=["is_read"])
            return Response({"success": True})
        except Notification.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class NotificationMarkAllReadView(APIView):
    """
    POST /api/accounts/notifications/mark-all-read/
    Marks all notifications as read for the user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        logger.debug(f"Marked {count} notifications as read for {request.user.username}")
        return Response({"marked_read": count})


class NotificationDeleteView(APIView):
    """
    DELETE /api/accounts/notifications/<id>/
    Deletes a single notification for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
            notif.delete()
            return Response({"success": True})
        except Notification.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class NotificationBulkActionView(APIView):
    """
    POST /api/accounts/notifications/bulk/
    Body: { "ids": [1,2,3], "action": "delete" | "mark_read" }
    Performs bulk delete or mark-as-read on the given notification IDs.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get("ids", [])
        action = request.data.get("action", "")
        if not ids or action not in ("delete", "mark_read"):
            return Response({"detail": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)
        qs = Notification.objects.filter(pk__in=ids, user=request.user)
        if action == "delete":
            count, _ = qs.delete()
            return Response({"deleted": count})
        else:
            count = qs.update(is_read=True)
            return Response({"marked_read": count})
