"""
PhonePe Payment Gateway Service
Handles all PhonePe SDK interactions
"""

import logging
from uuid import uuid4

from decouple import config
from phonepe.sdk.pg.common.exceptions import PhonePeException
from phonepe.sdk.pg.common.models.request.meta_info import MetaInfo
from phonepe.sdk.pg.common.models.request.refund_request import RefundRequest
from phonepe.sdk.pg.env import Env
from phonepe.sdk.pg.payments.v2.models.request.create_sdk_order_request import CreateSdkOrderRequest
from phonepe.sdk.pg.payments.v2.models.request.standard_checkout_pay_request import StandardCheckoutPayRequest
from phonepe.sdk.pg.payments.v2.standard_checkout_client import StandardCheckoutClient

logger = logging.getLogger(__name__)


class PhonePeService:
    """
    Service class for PhonePe Payment Gateway integration
    """

    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PhonePeService, cls).__new__(cls)
            cls._instance._initialize_client()
        return cls._instance

    def _initialize_client(self):
        """Initialize PhonePe SDK client"""
        try:
            client_id = config("CLIENT_ID")
            client_secret = config("CLIENT_SECRET")
            client_version = config("CLIENT_VERSION", cast=int)
            phonepe_env = config("PHONEPE_ENV", default="SANDBOX")

            # Set environment
            env = Env.SANDBOX if phonepe_env == "SANDBOX" else Env.PRODUCTION

            # Initialize client
            self._client = StandardCheckoutClient.get_instance(
                client_id=client_id,
                client_secret=client_secret,
                client_version=client_version,
                env=env,
                should_publish_events=False,
            )

            logger.info(f"PhonePe client initialized successfully in {phonepe_env} mode")

        except Exception as e:
            logger.error(f"Failed to initialize PhonePe client: {str(e)}")
            raise

    def get_client(self):
        """Get PhonePe client instance"""
        if self._client is None:
            self._initialize_client()
        return self._client

    def initiate_payment(
        self,
        amount,
        redirect_url,
        merchant_order_id=None,
        meta_info_dict=None,
        message=None,
        expire_after=300,
        disable_payment_retry=False,
    ):
        """
        Initiate a payment transaction

        Args:
            amount (int): Amount in paisa (minimum 100)
            redirect_url (str): URL to redirect after payment
            merchant_order_id (str, optional): Unique order ID. Generated if not provided
            meta_info_dict (dict, optional): Metadata (udf1-5)
            message (str, optional): Message for UPI collect
            expire_after (int, optional): Order expiry in seconds (default 3600)
            disable_payment_retry (bool, optional): Disable retry on failure

        Returns:
            dict: Response containing redirect_url, order_id, state, expire_at
        """
        try:
            # Generate unique order ID if not provided
            if not merchant_order_id:
                merchant_order_id = str(uuid4())

            # Create meta info
            meta_info = None
            if meta_info_dict:
                meta_info = MetaInfo(
                    udf1=meta_info_dict.get("udf1", ""),
                    udf2=meta_info_dict.get("udf2", ""),
                    udf3=meta_info_dict.get("udf3", ""),
                    udf4=meta_info_dict.get("udf4", ""),
                    udf5=meta_info_dict.get("udf5", ""),
                )

            # Build payment request
            pay_request = StandardCheckoutPayRequest.build_request(
                merchant_order_id=merchant_order_id,
                amount=amount,
                redirect_url=redirect_url,
                meta_info=meta_info,
                message=message,
                expire_after=expire_after,
                disable_payment_retry=disable_payment_retry,
            )

            # Execute payment
            client = self.get_client()
            response = client.pay(pay_request)

            logger.info(f"Payment initiated successfully: {merchant_order_id}")

            return {
                "success": True,
                "merchant_order_id": merchant_order_id,
                "redirect_url": response.redirect_url,
                "order_id": response.order_id,
                "state": response.state,
                "expire_at": response.expire_at,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe payment initiation failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during payment initiation: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_sdk_order(
        self, amount, redirect_url, merchant_order_id=None, meta_info_dict=None, disable_payment_retry=False
    ):
        """
        Create SDK order for mobile app integration

        Args:
            amount (int): Amount in paisa
            redirect_url (str): Redirect URL after payment
            merchant_order_id (str, optional): Unique order ID
            meta_info_dict (dict, optional): Metadata
            disable_payment_retry (bool, optional): Disable retry

        Returns:
            dict: Response containing token, order_id, state, expire_at
        """
        try:
            # Generate unique order ID if not provided
            if not merchant_order_id:
                merchant_order_id = str(uuid4())

            # Create meta info
            meta_info = None
            if meta_info_dict:
                meta_info = MetaInfo(
                    udf1=meta_info_dict.get("udf1", ""),
                    udf2=meta_info_dict.get("udf2", ""),
                    udf3=meta_info_dict.get("udf3", ""),
                )

            # Build SDK order request
            sdk_order_request = CreateSdkOrderRequest.build_standard_checkout_request(
                merchant_order_id=merchant_order_id,
                amount=amount,
                meta_info=meta_info,
                redirect_url=redirect_url,
                disable_payment_retry=disable_payment_retry,
            )

            # Create order
            client = self.get_client()
            response = client.create_sdk_order(sdk_order_request=sdk_order_request)

            logger.info(f"SDK order created successfully: {merchant_order_id}")

            return {
                "success": True,
                "merchant_order_id": merchant_order_id,
                "token": response.token,
                "order_id": response.order_id,
                "state": response.state,
                "expire_at": response.expire_at,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe SDK order creation failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during SDK order creation: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_order_status(self, merchant_order_id, details=False):
        """
        Get order status

        Args:
            merchant_order_id (str): Merchant order ID
            details (bool): If True, returns all payment attempts. If False, returns latest only

        Returns:
            dict: Order status response
        """
        try:
            client = self.get_client()
            response = client.get_order_status(merchant_order_id, details=details)

            logger.info(f"Order status fetched: {merchant_order_id} - State: {response.state}")

            return {
                "success": True,
                "order_id": response.order_id,
                "state": response.state,
                "amount": response.amount,
                "expire_at": response.expire_at,
                "meta_info": response.meta_info,
                "error_code": getattr(response, "error_code", None),
                "detailed_error_code": getattr(response, "detailed_error_code", None),
                "payment_details": response.payment_details,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe order status check failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during order status check: {str(e)}")
            return {"success": False, "error": str(e)}

    def initiate_refund(self, merchant_refund_id, original_merchant_order_id, amount):
        """
        Initiate a refund

        Args:
            merchant_refund_id (str): Unique refund ID
            original_merchant_order_id (str): Original order ID to refund
            amount (int): Refund amount in paisa

        Returns:
            dict: Refund response
        """
        try:
            # Build refund request
            refund_request = RefundRequest.build_refund_request(
                merchant_refund_id=merchant_refund_id,
                original_merchant_order_id=original_merchant_order_id,
                amount=amount,
            )

            # Execute refund
            client = self.get_client()
            response = client.refund(refund_request=refund_request)

            logger.info(f"Refund initiated: {merchant_refund_id} - State: {response.state}")

            return {
                "success": True,
                "merchant_refund_id": merchant_refund_id,
                "refund_id": response.refund_id,
                "state": response.state,
                "amount": response.amount,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe refund initiation failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during refund initiation: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_refund_status(self, merchant_refund_id):
        """
        Get refund status

        Args:
            merchant_refund_id (str): Merchant refund ID

        Returns:
            dict: Refund status response
        """
        try:
            client = self.get_client()
            response = client.get_refund_status(merchant_refund_id=merchant_refund_id)

            logger.info(f"Refund status fetched: {merchant_refund_id} - State: {response.state}")

            return {
                "success": True,
                "merchant_id": response.merchant_id,
                "merchant_refund_id": response.merchant_refund_id,
                "original_merchant_order_id": response.original_merchant_order_id,
                "amount": response.amount,
                "state": response.state,
                "payment_details": response.payment_details,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe refund status check failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during refund status check: {str(e)}")
            return {"success": False, "error": str(e)}

    def validate_callback(self, username, password, authorization_header, callback_response_body):
        """
        Validate webhook/callback from PhonePe

        Args:
            username (str): Configured callback username
            password (str): Configured callback password
            authorization_header (str): Authorization header value
            callback_response_body (str): Response body as string

        Returns:
            dict: Validated callback response
        """
        try:
            client = self.get_client()
            response = client.validate_callback(
                username=username,
                password=password,
                callback_header_data=authorization_header,
                callback_response_data=callback_response_body,
            )

            # Extract callback data - it's an object, convert to dict
            callback_data_dict = {}
            if hasattr(response, "callback_data") and response.callback_data:
                if hasattr(response.callback_data, "__dict__"):
                    callback_data_dict = response.callback_data.__dict__
                else:
                    callback_data_dict = response.callback_data

            # Extract event type from callback data
            callback_type = callback_data_dict.get("event", "UNKNOWN")

            logger.info(f"Callback validated: Type={callback_type}")

            return {
                "success": True,
                "callback_type": callback_type,
                "callback_data": callback_data_dict,
            }

        except PhonePeException as e:
            logger.error(f"PhonePe callback validation failed: {e.message} (Code: {e.code})")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
                "http_status_code": e.http_status_code,
                "data": e.data,
            }
        except Exception as e:
            logger.error(f"Unexpected error during callback validation: {str(e)}")
            return {"success": False, "error": str(e)}


phonepe_service = PhonePeService()
