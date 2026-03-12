"""
Refund initiation view.
Handles initiating refunds via PhonePe for completed payments.
"""
import logging
from uuid import uuid4

from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payments.models import Payment, Refund
from payments.serializers import InitiateRefundSerializer
from payments.services import phonepe_service

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_refund(request):
    """
    Initiate a refund (Admin/Host only)

    Request Body:
    {
        "payment_id": 1,
        "amount": 299.00,
        "reason": "Tournament cancelled"
    }
    """
    # Check if user is staff or host
    if not (request.user.is_staff or hasattr(request.user, "host_profile")):
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

    serializer = InitiateRefundSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        payment = Payment.objects.get(id=data["payment_id"])

        # Generate unique refund ID
        merchant_refund_id = f"REF_{uuid4().hex[:16].upper()}"

        # Convert amount to paisa
        amount_paisa = int(data["amount"] * 100)

        # Create refund record
        with transaction.atomic():
            refund = Refund.objects.create(
                merchant_refund_id=merchant_refund_id,
                payment=payment,
                amount=data["amount"],
                amount_paisa=amount_paisa,
                reason=data.get("reason", ""),
                status="pending",
            )

            # Initiate refund with PhonePe
            phonepe_response = phonepe_service.initiate_refund(
                merchant_refund_id=merchant_refund_id,
                original_merchant_order_id=payment.merchant_order_id,
                amount=amount_paisa,
            )

            if not phonepe_response.get("success"):
                refund.status = "failed"
                refund.error_code = phonepe_response.get("error_code", "")
                refund.save()

                return Response(
                    {"error": "Failed to initiate refund", "details": phonepe_response.get("error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Update refund with PhonePe response
            refund.phonepe_refund_id = phonepe_response.get("refund_id")
            refund.status = phonepe_response.get("state", "pending").lower()
            refund.callback_data = phonepe_response
            refund.save()

            logger.info(f"Refund initiated: {merchant_refund_id} for payment {payment.merchant_order_id}")

            return Response(
                {
                    "success": True,
                    "merchant_refund_id": merchant_refund_id,
                    "phonepe_refund_id": phonepe_response.get("refund_id"),
                    "state": phonepe_response.get("state"),
                    "amount": str(data["amount"]),
                },
                status=status.HTTP_200_OK,
            )

    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error initiating refund: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
