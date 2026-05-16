from django.conf import settings
from django.core.mail import send_mail
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from communications.models import IssueReport


class ContactFormView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        name = request.data.get('name', '').strip()
        phone = request.data.get('phone', '').strip()
        email = request.data.get('email', '').strip()
        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()

        if not name or not message:
            return Response(
                {'error': 'Name and message are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = f"From: {name}\nPhone: {phone}\nEmail: {email}\n\n{message}"
        full_subject = f"[Contact] {subject or 'No subject'} — from {name}"

        support_email = getattr(settings, 'SUPPORT_EMAIL', settings.DEFAULT_FROM_EMAIL)

        try:
            send_mail(
                full_subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [support_email],
                fail_silently=False,
            )
            return Response({'success': True})
        except Exception:
            return Response(
                {'error': 'Failed to send email. Please try again later.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReportIssueView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()

        if not title or not description:
            return Response(
                {'error': 'Title and description are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = IssueReport.objects.create(
            issue_type=request.data.get('issueType', 'other'),
            priority=request.data.get('priority', 'medium'),
            title=title,
            description=description,
            steps_to_reproduce=request.data.get('steps', ''),
            reporter_name=request.data.get('reporterName', ''),
            reporter_email=request.data.get('reporterEmail', ''),
            anonymous=bool(request.data.get('anonymous', False)),
            submitted_by=request.user if request.user.is_authenticated else None,
        )

        return Response({'success': True, 'report_id': report.id})
