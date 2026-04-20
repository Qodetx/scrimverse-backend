import io
import json
import logging
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DataExportRequest, HostProfile, Notification, PlayerProfile, Team, TeamMember, User
from accounts.serializers import (
    HostProfileSerializer,
    PlayerProfileSerializer,
    UserSerializer,
)
from accounts.tasks import generate_data_export
from accounts.validators import validate_aadhar_image

logger = logging.getLogger(__name__)


class PlayerProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Player Profile
    GET/PUT /api/accounts/player/profile/<id>/
    The <id> is the User ID, not the PlayerProfile PK.
    """

    serializer_class = PlayerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PlayerProfile.objects.all()

    def get_object(self):
        user_id = self.kwargs.get("pk")
        try:
            profile = PlayerProfile.objects.get(user__id=user_id)
        except PlayerProfile.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound(f"Player profile not found for user id {user_id}")
        self.check_object_permissions(self.request, profile)
        return profile


class CurrentPlayerProfileView(APIView):
    """
    Update current player's profile
    PATCH /api/accounts/player/profile/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        user = request.user
        if user.user_type != "player":
            return Response({"error": "Only players can update player profiles"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "player_profile"):
            return Response({"error": "Player profile not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PlayerProfileSerializer(user.player_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.debug(f"Player profile updated - User: {user.id}, Username: {user.username}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HostProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and Update Host Profile
    GET/PUT /api/accounts/host/profile/<id>/
    """

    queryset = HostProfile.objects.all()
    serializer_class = HostProfileSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


class CurrentHostProfileView(APIView):
    """
    Update current host's profile
    PATCH /api/accounts/host/profile/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        user = request.user
        if user.user_type != "host":
            return Response({"error": "Only hosts can update host profiles"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "host_profile"):
            return Response({"error": "Host profile not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = HostProfileSerializer(user.host_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.debug(f"Host profile updated - User: {user.id}, Username: {user.username}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UploadAadharView(APIView):
    """
    Upload Aadhar card for host verification
    POST /api/accounts/host/upload-aadhar/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.user_type != "host":
            return Response({"error": "Only hosts can upload Aadhar cards"}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(user, "host_profile"):
            return Response({"error": "Host profile not found"}, status=status.HTTP_404_NOT_FOUND)

        host_profile = user.host_profile

        # Get uploaded files
        aadhar_front = request.FILES.get("aadhar_card_front")
        aadhar_back = request.FILES.get("aadhar_card_back")

        if not aadhar_front or not aadhar_back:
            return Response(
                {"error": "Both front and back images of Aadhar card are required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate files using the model's validators
        try:
            validate_aadhar_image(aadhar_front)
            validate_aadhar_image(aadhar_back)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Update host profile
        host_profile.aadhar_card_front = aadhar_front
        host_profile.aadhar_card_back = aadhar_back
        host_profile.aadhar_uploaded_at = timezone.now()
        host_profile.verification_status = "pending"
        host_profile.save()

        return Response(
            {
                "message": "Aadhar card uploaded successfully. Your verification is pending admin approval.",
                "verification_status": host_profile.verification_status,
                "aadhar_uploaded_at": host_profile.aadhar_uploaded_at,
            },
            status=status.HTTP_200_OK,
        )


class UserDetailView(APIView):
    """
    Get any user's public profile by ID
    GET /api/accounts/users/{id}/
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to view profiles

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user)

        profile_data = None
        if user.user_type == "player" and hasattr(user, "player_profile"):
            profile_data = PlayerProfileSerializer(user.player_profile).data
        elif user.user_type == "host" and hasattr(user, "host_profile"):
            profile_data = HostProfileSerializer(user.host_profile).data

        return Response({"user": serializer.data, "profile": profile_data}, status=status.HTTP_200_OK)


class PlayerUsernameSearchView(APIView):
    """
    Search for players by username (for team registration autocomplete)
    GET /api/accounts/players/search/?q=<username>
    Returns list of matching player usernames and details
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to search

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        for_team = request.query_params.get("for_team", "false").lower() == "true"
        game = request.query_params.get("game", None)

        if not query or len(query) < 2:
            return Response({"results": []}, status=status.HTTP_200_OK)

        # Base query - search for players by username
        players = PlayerProfile.objects.filter(
            user__username__icontains=query, user__user_type="player"
        ).select_related("user")

        # If searching for team invites, exclude players already in a permanent team for the same game
        if for_team:
            # Exclude players already in a permanent team for this specific game
            # (one permanent team per player per game — different games are allowed)
            team_filter = {"team__is_temporary": False}
            if game:
                team_filter["team__game"] = game
            users_in_same_game_team = TeamMember.objects.filter(**team_filter).values_list("user_id", flat=True)
            players = players.exclude(user_id__in=users_in_same_game_team)

            # Exclude current user if authenticated (they're already the captain)
            if request.user.is_authenticated:
                players = players.exclude(user=request.user)

        # Order exact matches first, then partial matches, then alphabetically
        from django.db.models import Case, IntegerField, Value, When
        players = players.annotate(
            exact_match=Case(
                When(user__username__iexact=query, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("exact_match", "user__username")

        # Apply slice AFTER all filters
        players = players[:10]

        results = [
            {
                "id": player.user.id,
                "username": player.user.username,
                "email": player.user.email,
                "profile_picture": player.user.profile_picture.url if player.user.profile_picture else None,
                "in_team": TeamMember.objects.filter(user=player.user, team__is_temporary=False).exists()
                if not for_team
                else False,
            }
            for player in players
        ]

        # Handle absolute URLs if request is available
        for res in results:
            if res["profile_picture"] and not res["profile_picture"].startswith("http"):
                res["profile_picture"] = request.build_absolute_uri(res["profile_picture"])

        logger.debug(f"Player search results - Query: {query}, For Team: {for_team}, Results: {len(results)}")
        return Response({"results": results}, status=status.HTTP_200_OK)


class HostSearchView(APIView):
    """
    Search for hosts by username or organization name
    GET /api/accounts/hosts/search/?q=<query>
    Returns list of matching hosts and details
    """

    permission_classes = [permissions.AllowAny]  # Allow guests to search

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if not query or len(query) < 2:
            return Response({"results": []}, status=status.HTTP_200_OK)

        # Search for hosts by username
        hosts = HostProfile.objects.filter(user__username__icontains=query, user__user_type="host").select_related(
            "user"
        )[
            :10
        ]  # Limit to 10 results

        results = [
            {
                "id": host.id,  # Return host profile ID
                "username": host.user.username,
                "email": host.user.email,
                "verified": host.verified,
                "profile_picture": host.user.profile_picture.url if host.user.profile_picture else None,
            }
            for host in hosts
        ]

        # Handle absolute URLs if request is available
        for res in results:
            if res["profile_picture"] and not res["profile_picture"].startswith("http"):
                res["profile_picture"] = request.build_absolute_uri(res["profile_picture"])

        logger.debug(f"Host search results - Query: {query}, Results: {len(results)}")
        return Response({"results": results}, status=status.HTTP_200_OK)


class ExportDataView(APIView):
    """
    Download all user data as a JSON file (GDPR-style data export).
    GET /api/accounts/export-data/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Core user data
        data = {
            "account": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "user_type": user.user_type,
                "phone_number": user.phone_number,
                "is_email_verified": user.is_email_verified,
                "date_joined": user.date_joined.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
        }

        # Player profile
        if user.user_type == "player" and hasattr(user, "player_profile"):
            pp = user.player_profile
            data["player_profile"] = {
                "in_game_name": pp.in_game_name,
                "game_id": pp.game_id,
                "preferred_games": pp.preferred_games,
                "game_profiles": pp.game_profiles,
                "bio": pp.bio,
                "total_tournaments_participated": pp.total_tournaments_participated,
                "total_wins": pp.total_wins,
            }

        # Host profile
        if user.user_type == "host" and hasattr(user, "host_profile"):
            hp = user.host_profile
            data["host_profile"] = {
                "bio": hp.bio,
                "website": hp.website,
                "total_tournaments_hosted": hp.total_tournaments_hosted,
                "rating": float(hp.rating),
                "verified": hp.verified,
            }

        # Teams
        team_memberships = TeamMember.objects.filter(user=user).select_related("team")
        data["teams"] = [
            {
                "team_name": tm.team.name,
                "team_id": tm.team.id,
                "role": tm.role,
                "joined_at": tm.joined_at.isoformat() if hasattr(tm, "joined_at") and tm.joined_at else None,
                "is_temporary": tm.team.is_temporary,
            }
            for tm in team_memberships
        ]

        # Tournament registrations
        from tournaments.models import TournamentRegistration
        registrations = TournamentRegistration.objects.filter(
            player__user=user
        ).select_related("tournament")
        data["tournament_registrations"] = [
            {
                "tournament_name": reg.tournament.name,
                "tournament_id": reg.tournament.id,
                "event_mode": reg.tournament.event_mode,
                "registered_at": reg.registered_at.isoformat() if reg.registered_at else None,
                "status": reg.status,
            }
            for reg in registrations
        ]

        # Notifications
        notifications = Notification.objects.filter(user=user).order_by("-created_at")[:100]
        data["notifications"] = [
            {
                "type": n.type,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ]

        # Return as downloadable JSON file
        response = HttpResponse(
            json.dumps(data, indent=2, default=str),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="scrimverse_data_{user.username}.json"'
        logger.info(f"Data export - User: {user.id}, Username: {user.username}")
        return response


class DeleteAccountView(APIView):
    """
    Soft-delete (deactivate) user account. Requires password confirmation.
    POST /api/accounts/delete-account/
    Body: { "password": "current_password" }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        password = request.data.get("password", "").strip()

        if not password:
            return Response(
                {"error": "Password is required to confirm account deletion."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Google OAuth users have unusable passwords — allow deletion without password check
        if user.has_usable_password() and not user.check_password(password):
            return Response(
                {"error": "Incorrect password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Soft delete: deactivate account
        user.is_active = False
        user.save(update_fields=["is_active"])

        logger.info(f"Account deactivated (soft delete) - User: {user.id}, Username: {user.username}")
        return Response(
            {"message": "Your account has been deleted. You will be logged out."},
            status=status.HTTP_200_OK,
        )


# ============================================================================
# DATA EXPORT (Token-based email flow)
# ============================================================================


class RequestDataExportView(APIView):
    """
    Request a data export. Queues a Celery task to collect data and email a link.
    POST /api/accounts/request-data-export/

    Rate limited: 1 request per 24 hours.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # Rate limit: 1 request per 10 minutes
        recent_cutoff = timezone.now() - timedelta(minutes=10)
        recent_export = DataExportRequest.objects.filter(
            user=user,
            created_at__gte=recent_cutoff,
        ).first()

        if recent_export:
            retry_after = recent_export.created_at + timedelta(minutes=10)
            minutes_left = max(1, int((retry_after - timezone.now()).total_seconds() / 60))
            if minutes_left >= 60:
                retry_str = f"{minutes_left // 60}h {minutes_left % 60}m" if minutes_left % 60 else f"{minutes_left // 60}h"
            else:
                retry_str = f"{minutes_left}m"
            return Response(
                {
                    "error": "You already requested a data export recently. Check your email.",
                    "retry_after_minutes": minutes_left,
                    "retry_after_str": retry_str,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Queue the Celery task
        generate_data_export.delay(user.id)

        logger.info(f"Data export requested - User: {user.id}, Username: {user.username}")
        return Response(
            {"message": "Check your email -- your data report will arrive shortly."},
            status=status.HTTP_202_ACCEPTED,
        )


class DataExportDetailView(APIView):
    """
    Retrieve exported data by token. No authentication required -- the token IS the auth.
    GET /api/accounts/data-export/<uuid:token>/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            export = DataExportRequest.objects.get(token=token)
        except DataExportRequest.DoesNotExist:
            return Response(
                {"error": "This data export link is invalid."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not export.is_valid():
            return Response(
                {"error": "This data export link has expired."},
                status=status.HTTP_410_GONE,
            )

        return Response(
            {
                "data": export.data,
                "created_at": export.created_at.isoformat(),
                "expires_at": export.expires_at.isoformat(),
                "username": export.user.username,
            },
            status=status.HTTP_200_OK,
        )


class DataExportPDFView(APIView):
    """
    Generate and download a PDF version of the data export.
    GET /api/accounts/data-export/<uuid:token>/pdf/

    No authentication required -- the token IS the auth.
    Uses reportlab to generate the PDF on the fly.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            export = DataExportRequest.objects.get(token=token)
        except DataExportRequest.DoesNotExist:
            return Response(
                {"error": "This data export link is invalid."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not export.is_valid():
            return Response(
                {"error": "This data export link has expired."},
                status=status.HTTP_410_GONE,
            )

        data = export.data

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError:
            logger.error("reportlab is not installed. Cannot generate PDF.")
            return Response(
                {"error": "PDF generation is not available. Please install reportlab."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        buffer = io.BytesIO()

        header_height = 0.9 * inch
        footer_height = 0.5 * inch

        def draw_header_footer(canvas, doc):
            canvas.saveState()
            w, h = A4

            # ── Header band ──────────────────────────────────────────────
            canvas.setFillColor(colors.HexColor("#0f0f1a"))
            canvas.rect(0, h - header_height, w, header_height, fill=1, stroke=0)

            # Logo text: "SCRIM" white + "VERSE" purple
            canvas.setFont("Helvetica-Bold", 18)
            canvas.setFillColor(colors.white)
            canvas.drawString(40, h - header_height + 30, "SCRIM")
            canvas.setFillColor(colors.HexColor("#a855f7"))
            scrim_w = canvas.stringWidth("SCRIM", "Helvetica-Bold", 18)
            canvas.drawString(40 + scrim_w, h - header_height + 30, "VERSE")

            # Tagline
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#888888"))
            canvas.drawString(40, h - header_height + 16, "Where Practice Meets Passion  ·  support@scrimverse.com")

            # Right: doc title
            canvas.setFont("Helvetica-Bold", 10)
            canvas.setFillColor(colors.white)
            title_text = "Player Data Report"
            title_w = canvas.stringWidth(title_text, "Helvetica-Bold", 10)
            canvas.drawString(w - 40 - title_w, h - header_height + 28, title_text)

            # Generated date
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#aaaaaa"))
            date_text = export.created_at.strftime("Generated %B %d, %Y")
            date_w = canvas.stringWidth(date_text, "Helvetica", 8)
            canvas.drawString(w - 40 - date_w, h - header_height + 16, date_text)

            # ── Footer band ───────────────────────────────────────────────
            canvas.setFillColor(colors.HexColor("#f4f4f4"))
            canvas.rect(0, 0, w, footer_height, fill=1, stroke=0)
            canvas.setStrokeColor(colors.HexColor("#cccccc"))
            canvas.setLineWidth(0.5)
            canvas.line(0, footer_height, w, footer_height)

            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(colors.HexColor("#666666"))
            canvas.drawString(40, footer_height - 16,
                "This report is confidential and was generated by ScrimVerse for the account holder only.")
            canvas.drawString(40, footer_height - 26,
                "For queries contact support@scrimverse.com  ·  scrimverse.com")

            # Page number
            canvas.setFont("Helvetica", 7.5)
            page_num = f"Page {doc.page}"
            pn_w = canvas.stringWidth(page_num, "Helvetica", 7.5)
            canvas.drawString(w - 40 - pn_w, footer_height - 20, page_num)

            canvas.restoreState()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=header_height + 20,
            bottomMargin=footer_height + 20,
        )

        styles = getSampleStyleSheet()
        section_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading2"],
            fontSize=13,
            spaceBefore=18,
            spaceAfter=8,
            textColor=colors.HexColor("#1a1a2e"),
            fontName="Helvetica-Bold",
        )
        body_style = ParagraphStyle(
            "ExportBody",
            parent=styles["Normal"],
            fontSize=10,
            spaceAfter=4,
        )
        meta_style = ParagraphStyle(
            "MetaLine",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#555555"),
            spaceAfter=12,
        )

        elements = []

        # User + generated info line (below header)
        username = export.user.username
        elements.append(Paragraph(
            f"<b>Account:</b> {username} &nbsp;&nbsp; "
            f"<b>Email:</b> {export.user.email} &nbsp;&nbsp; "
            f"<b>Expires:</b> {export.expires_at.strftime('%B %d, %Y')}",
            meta_style,
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # ── Account Info ─────────────────────────────────────────────────
        account = data.get("account", {})
        elements.append(Paragraph("Account Information", section_style))
        account_rows = [
            ["Field", "Value"],
            ["Username", account.get("username", "N/A")],
            ["Email", account.get("email", "N/A")],
            ["Phone", account.get("phone_number", "N/A") or "Not set"],
            ["User Type", account.get("user_type", "N/A")],
            ["Email Verified", "Yes" if account.get("is_email_verified") else "No"],
            ["Member Since", account.get("date_joined", "N/A")[:10] if account.get("date_joined") else "N/A"],
        ]
        t = Table(account_rows, colWidths=[2 * inch, 4 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.2 * inch))

        # ── Gaming Profiles ──────────────────────────────────────────────
        player_profile = data.get("player_profile", {})
        game_profiles = player_profile.get("game_profiles", {})
        if game_profiles:
            elements.append(Paragraph("Gaming Profiles", section_style))
            gp_rows = [["Game", "In-Game Name", "Game ID"]]
            for game, info in game_profiles.items():
                if isinstance(info, dict):
                    ign = info.get("ign", "N/A") or "N/A"
                    gid = info.get("game_id", "N/A") or "N/A"
                    gp_rows.append([game, ign, gid])
            if len(gp_rows) > 1:
                t = Table(gp_rows, colWidths=[1.5 * inch, 2.5 * inch, 2 * inch])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 0.2 * inch))

        # ── Tournament History ───────────────────────────────────────────
        tournaments = data.get("tournament_registrations", [])
        if tournaments:
            elements.append(Paragraph("Tournament History", section_style))
            t_rows = [["Tournament", "Mode", "Status", "Date"]]
            for reg in tournaments:
                t_rows.append([
                    reg.get("tournament_name", "N/A")[:40],
                    reg.get("event_mode", "N/A"),
                    reg.get("status", "N/A"),
                    (reg.get("registered_at", "") or "")[:10],
                ])
            t = Table(t_rows, colWidths=[2.2 * inch, 1.2 * inch, 1.2 * inch, 1.4 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.2 * inch))

        # ── Team History ─────────────────────────────────────────────────
        teams = data.get("teams", [])
        if teams:
            elements.append(Paragraph("Team History", section_style))
            tm_rows = [["Team", "Role", "Type"]]
            for team in teams:
                role = "Captain" if team.get("is_captain") else "Member"
                team_type = "Temporary" if team.get("is_temporary") else "Permanent"
                tm_rows.append([team.get("team_name", "N/A"), role, team_type])
            t = Table(tm_rows, colWidths=[2.5 * inch, 1.5 * inch, 2 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.2 * inch))

        # ── Payment History ──────────────────────────────────────────────
        payments = data.get("payment_history", [])
        if payments:
            elements.append(Paragraph("Payment History", section_style))
            p_rows = [["Order ID", "Type", "Amount (INR)", "Status", "Date"]]
            for p in payments[:50]:
                amount = p.get("amount")
                amount_str = f"{amount}" if amount is not None else "N/A"
                p_rows.append([
                    str(p.get("merchant_order_id", "N/A") or "N/A")[:22],
                    str(p.get("payment_type", "N/A") or "N/A"),
                    amount_str,
                    str(p.get("status", "N/A") or "N/A"),
                    str(p.get("created_at", "") or "")[:10],
                ])
            t = Table(p_rows, colWidths=[1.8 * inch, 1.2 * inch, 1.1 * inch, 1 * inch, 1.1 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.2 * inch))
        else:
            elements.append(Paragraph("Payment History", section_style))
            elements.append(Paragraph("No payment records found.", body_style))
            elements.append(Spacer(1, 0.2 * inch))

        elements.append(Spacer(1, 0.2 * inch))

        doc.build(elements, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
        buffer.seek(0)

        response = HttpResponse(buffer.read(), content_type="application/pdf")
        username = export.user.username
        response["Content-Disposition"] = f'attachment; filename="scrimverse_data_{username}.pdf"'
        logger.info(f"PDF data export downloaded - User: {export.user.id}, Token: {token}")
        return response
