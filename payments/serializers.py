from rest_framework import serializers

from .models import Payment, Refund


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""

    user_username = serializers.CharField(source="user.username", read_only=True)
    tournament_title = serializers.CharField(source="tournament.title", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "merchant_order_id",
            "phonepe_order_id",
            "phonepe_transaction_id",
            "payment_type",
            "amount",
            "amount_paisa",
            "user",
            "user_username",
            "player_profile",
            "host_profile",
            "tournament",
            "tournament_title",
            "registration",
            "status",
            "payment_mode",
            "instrument_type",
            "redirect_url",
            "callback_data",
            "error_code",
            "detailed_error_code",
            "meta_info",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "phonepe_order_id",
            "phonepe_transaction_id",
            "redirect_url",
            "callback_data",
            "created_at",
            "updated_at",
            "completed_at",
        ]


class InitiatePaymentSerializer(serializers.Serializer):
    """Serializer for initiating payment"""

    payment_type = serializers.ChoiceField(choices=["tournament_plan", "scrim_plan", "entry_fee"])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    tournament_id = serializers.IntegerField(required=False, allow_null=True)
    registration_id = serializers.IntegerField(required=False, allow_null=True)
    redirect_url = serializers.URLField(required=False)

    def validate_amount(self, value):
        """Validate amount is non-negative (allow ₹0 for free tournaments)"""
        if value < 0:
            raise serializers.ValidationError("Amount cannot be negative")
        return value

    def validate(self, data):
        """Cross-field validation"""
        payment_type = data.get("payment_type")

        # For tournament/scrim plans, tournament_id is required
        if payment_type in ["tournament_plan", "scrim_plan"]:
            if not data.get("tournament_id"):
                raise serializers.ValidationError(
                    {"tournament_id": "Tournament ID is required for tournament/scrim plan payments"}
                )

        # For entry fees, registration_id is required
        if payment_type == "entry_fee":
            if not data.get("registration_id"):
                raise serializers.ValidationError(
                    {"registration_id": "Registration ID is required for entry fee payments"}
                )

        return data


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status response"""

    merchant_order_id = serializers.CharField()


class RefundSerializer(serializers.ModelSerializer):
    """Serializer for Refund model"""

    payment_merchant_order_id = serializers.CharField(source="payment.merchant_order_id", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "merchant_refund_id",
            "phonepe_refund_id",
            "payment",
            "payment_merchant_order_id",
            "amount",
            "amount_paisa",
            "reason",
            "status",
            "callback_data",
            "error_code",
            "detailed_error_code",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "phonepe_refund_id",
            "callback_data",
            "created_at",
            "updated_at",
            "completed_at",
        ]


class InitiateRefundSerializer(serializers.Serializer):
    """Serializer for initiating refund"""

    payment_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        """Validate amount is at least 1 INR (100 paisa)"""
        if value < 1:
            raise serializers.ValidationError("Refund amount must be at least ₹1")
        return value

    def validate_payment_id(self, value):
        """Validate payment exists and is completed"""
        try:
            payment = Payment.objects.get(id=value)
            if payment.status != "completed":
                raise serializers.ValidationError("Can only refund completed payments")
            return value
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Payment not found")

    def validate(self, data):
        """Validate refund amount doesn't exceed payment amount"""
        payment = Payment.objects.get(id=data["payment_id"])

        # Calculate total already refunded
        total_refunded = sum(refund.amount for refund in payment.refunds.filter(status__in=["accepted", "completed"]))

        # Check if refund amount is valid
        if data["amount"] > (payment.amount - total_refunded):
            raise serializers.ValidationError(
                {"amount": f"Refund amount cannot exceed remaining amount: ₹{payment.amount - total_refunded}"}
            )

        return data
