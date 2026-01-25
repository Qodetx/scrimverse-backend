from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PlanPricing


class PlanPricingView(APIView):
    """
    Get current plan pricing for tournaments and scrims
    GET /api/tournaments/plan-pricing/
    """

    permission_classes = []  # Public endpoint

    def get(self, request):
        """Return current plan prices"""
        pricing = {
            "tournament": {
                "basic": float(PlanPricing.get_price("TOURNAMENT", "basic")),
                "featured": float(PlanPricing.get_price("TOURNAMENT", "featured")),
                "premium": float(PlanPricing.get_price("TOURNAMENT", "premium")),
            },
            "scrim": {
                "basic": float(PlanPricing.get_price("SCRIM", "basic")),
                "featured": float(PlanPricing.get_price("SCRIM", "featured")),
                "premium": float(PlanPricing.get_price("SCRIM", "premium")),
            },
        }

        return Response({"success": True, "pricing": pricing}, status=status.HTTP_200_OK)
