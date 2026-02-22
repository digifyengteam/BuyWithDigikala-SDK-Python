
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import os
import time
from typing import List, Optional, Any, Dict

try:
    import requests
except ImportError:
    raise ImportError("Please install the 'requests' library: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BWDK_BASE_URL", "https://bwdk-backend.digify.shop/orders/api/v1")


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ItemOption:
    """Represents a product option (color, size, etc.)"""
    type_name: str          # e.g. "color", "size", "other"
    name: str               # e.g. "قرمز", "XL"
    value: str              # e.g. "#FF0000", "xl"
    is_color: bool = False  # True only for color options

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type_name": self.type_name,
            "name": self.name,
            "value": self.value,
            "is_color": self.is_color,
        }


@dataclass
class OrderItem:
    """Represents a single item in the shopping cart."""
    name: str
    primary_amount: int        # Original price (before discount), per unit
    amount: int                # Final price (after store discount), per unit
    count: int                 # Quantity in cart
    discount_amount: int       # Coupon/promo discount per unit (not store discount)
    tax_amount: int            # Tax amount per unit
    image_link: str
    options: List[ItemOption] = field(default_factory=list)
    preparation_time: Optional[int] = None  # in days
    weight: Optional[int] = None            # in grams
    has_tax: Optional[bool] = None
    tax_percent: Optional[int] = None
    variant_id: Optional[int] = None        # maps to "id" field

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "primary_amount": self.primary_amount,
            "amount": self.amount,
            "count": self.count,
            "discount_amount": self.discount_amount,
            "tax_amount": self.tax_amount,
            "image_link": self.image_link,
            "options": [opt.to_dict() for opt in self.options],
        }
        if self.variant_id is not None:
            d["id"] = self.variant_id
        if self.preparation_time is not None:
            d["preparation_time"] = self.preparation_time
        if self.weight is not None:
            d["weight"] = self.weight
        if self.has_tax is not None:
            d["has_tax"] = self.has_tax
        if self.tax_percent is not None:
            d["tax_percent"] = self.tax_percent
        return d


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

@dataclass
class CreateOrderResponse:
    order_start_url: str
    order_uuid: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreateOrderResponse":
        return cls(
            order_start_url=data["order_start_url"],
            order_uuid=data.get("Order_uuid") or data.get("order_uuid", ""),
        )


@dataclass
class OrderDetails:
    """Full order details returned by the Get Order endpoint."""
    raw: Dict[str, Any]

    # Convenience properties
    @property
    def id(self) -> int:
        return self.raw.get("id")

    @property
    def order_uuid(self) -> str:
        return self.raw.get("order_uuid", "")

    @property
    def status(self) -> int:
        return self.raw.get("status")

    @property
    def status_display(self) -> str:
        return self.raw.get("status_display", "")

    @property
    def is_paid(self) -> bool:
        return self.raw.get("is_paid", False)

    @property
    def final_amount(self) -> int:
        return self.raw.get("final_amount", 0)

    @property
    def total_paid_amount(self) -> int:
        return self.raw.get("total_paid_amount", 0)

    @property
    def merchant_order_id(self) -> str:
        return self.raw.get("merchant_order_id", "")

    @property
    def destination_address(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("destination_address")

    @property
    def user(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("user")

    @property
    def payment(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("payment")

    @property
    def selected_shipping_method(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("selected_shipping_method")

    def __repr__(self) -> str:
        return (
            f"<OrderDetails uuid={self.order_uuid!r} "
            f"status={self.status_display!r} is_paid={self.is_paid}>"
        )


@dataclass
class VerifyOrderResponse:
    raw: Dict[str, Any]

    @property
    def success(self) -> bool:
        return "error" not in self.raw

    @property
    def error(self) -> Optional[str]:
        return self.raw.get("error")


@dataclass
class RefundOrderResponse:
    message: str
    order_uuid: str
    status: int
    status_display: str
    refund_reason: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefundOrderResponse":
        return cls(
            message=data.get("message", ""),
            order_uuid=data.get("order_uuid", ""),
            status=data.get("status", 0),
            status_display=data.get("status_display", ""),
            refund_reason=data.get("refund_reason", ""),
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BWDKError(Exception):
    """Base exception for all BWDK SDK errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __repr__(self) -> str:
        return f"BWDKError(status_code={self.status_code}, message={str(self)!r})"


class BWDKAuthError(BWDKError):
    """Raised when the API key is invalid or missing."""


class BWDKValidationError(BWDKError):
    """Raised when the request payload is invalid (HTTP 400)."""


class BWDKNotFoundError(BWDKError):
    """Raised when the requested resource is not found (HTTP 404)."""


class BWDKServerError(BWDKError):
    """Raised when the BWDK server returns a 5xx error."""


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class BWDKClient:
    """
    Python client for the BuyWithDigikala (BWDK) REST API.

    Args:
        api_key (str): Your API key obtained from the Digify team.
        timeout (int): Request timeout in seconds (default: 30).
        session (requests.Session, optional): Custom requests session for testing/proxying.
    """

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        if not api_key:
            raise ValueError("api_key must not be empty.")
        self.api_key = api_key
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(self._auth_headers())

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Parse response and raise appropriate exceptions on error."""
        try:
            body = response.json()
        except Exception:
            body = response.text

        if response.status_code == 401 or response.status_code == 403:
            raise BWDKAuthError(
                "Authentication failed. Check your API key.",
                status_code=response.status_code,
                response_body=body,
            )
        if response.status_code == 400:
            raise BWDKValidationError(
                f"Validation error: {body}",
                status_code=400,
                response_body=body,
            )
        if response.status_code == 404:
            raise BWDKNotFoundError(
                "Resource not found.",
                status_code=404,
                response_body=body,
            )
        if response.status_code >= 500:
            raise BWDKServerError(
                f"BWDK server error (HTTP {response.status_code}): {body}",
                status_code=response.status_code,
                response_body=body,
            )
        if not response.ok:
            raise BWDKError(
                f"Unexpected error (HTTP {response.status_code}): {body}",
                status_code=response.status_code,
                response_body=body,
            )

        return body if isinstance(body, dict) else {"raw": body}

    # ------------------------------------------------------------------
    # Public API Methods
    # ------------------------------------------------------------------

    def create_order(
        self,
        merchant_unique_id: str,
        merchant_order_id: str,
        main_amount: int,
        final_amount: int,
        items: List[OrderItem],
        callback_url: str,
        reservation_expired_at: int,
        discount_amount: int = 0,
        tax_amount: int = 0,
        loyalty_amount: int = 0,
        preparation_time: Optional[int] = None,
        weight: Optional[int] = None,
    ) -> CreateOrderResponse:
        """
        Create a new BWDK order.

        Args:
            merchant_unique_id: A unique ID you generate and store (needed for verify).
            merchant_order_id: Your internal order ID.
            main_amount: Sum of all item prices (before coupon discount).
            final_amount: Amount the customer actually pays.
            items: List of OrderItem objects.
            callback_url: URL to redirect user after payment (no query params allowed).
                          Must be under your registered domain, max one subdomain level.
            reservation_expired_at: Unix UTC timestamp; must be at least 20 min from now.
            discount_amount: Total coupon/promo discount (not product price difference).
            tax_amount: Total tax for the cart.
            loyalty_amount: Loyalty points amount (usually 0).
            preparation_time: Max preparation time in days across all items (default: 2).
            weight: Total weight in grams (default: merchant panel average).

        Returns:
            CreateOrderResponse with order_uuid and order_start_url.

        Raises:
            BWDKValidationError: If the payload is invalid.
            BWDKAuthError: If the API key is invalid.
            BWDKServerError: On server-side errors.
        """
        if not items:
            raise ValueError("items list must not be empty.")

        min_reservation = int(time.time()) + 20 * 60
        if reservation_expired_at < min_reservation:
            raise ValueError(
                "reservation_expired_at must be at least 20 minutes from now."
            )

        payload: Dict[str, Any] = {
            "merchant_unique_id": merchant_unique_id,
            "merchant_order_id": str(merchant_order_id),
            "main_amount": main_amount,
            "final_amount": final_amount,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "loyalty_amount": loyalty_amount,
            "callback_url": callback_url,
            "reservation_expired_at": reservation_expired_at,
            "items": [item.to_dict() for item in items],
        }

        if preparation_time is not None:
            payload["preparation_time"] = preparation_time
        if weight is not None:
            payload["weight"] = weight

        response = self._session.post(
            self._url("create-order/"),
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        data = self._handle_response(response)
        return CreateOrderResponse.from_dict(data)

    def get_order(self, order_uuid: str) -> OrderDetails:
        """
        Retrieve full details of an order.

        IMPORTANT: Always call this after the user returns to your callback_url
        instead of trusting the query parameters — those can be tampered with.

        Args:
            order_uuid: The UUID returned by create_order (or from callback query params).

        Returns:
            OrderDetails object containing payment, address, user info, etc.

        Raises:
            BWDKNotFoundError: If the order UUID doesn't exist.
            BWDKAuthError: If the API key is invalid.
        """
        response = self._session.get(
            self._url(f"manager/{order_uuid}/"),
            timeout=self.timeout,
        )
        data = self._handle_response(response)
        return OrderDetails(raw=data)

    def verify_order(self, order_uuid: str, merchant_unique_id: str) -> VerifyOrderResponse:
        """
        Confirm receipt of a paid order.

        Must be called after get_order() confirms the order is PAID_BY_USER (status=7).
        Orders that are not verified cannot be settled/disbursed.

        Args:
            order_uuid: The order's UUID.
            merchant_unique_id: The same unique ID you used when creating the order.

        Returns:
            VerifyOrderResponse. Check .success and .error.

        Raises:
            BWDKValidationError: If order is not in PAID_BY_USER status.
            BWDKAuthError: If the API key is invalid.
        """
        payload = {"merchant_unique_id": merchant_unique_id}
        response = self._session.post(
            self._url(f"manager/{order_uuid}/verify/"),
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        data = self._handle_response(response)
        return VerifyOrderResponse(raw=data)

    def refund_order(self, order_uuid: str, reason: str, amount: int) -> RefundOrderResponse:
        """
        Request a full refund for an order.

        Note: Only full refunds are supported. Partial item refunds are not available.
        If the order has already been settled with the merchant, refund is not possible.

        Args:
            order_uuid: The order's UUID.
            reason: Human-readable reason for the refund (e.g. "انصراف مشتری از خرید").
            amount: The refund amount in Rials/Tomans (must match original payment).

        Returns:
            RefundOrderResponse with status and confirmation message.

        Raises:
            BWDKValidationError: If refund is not possible (e.g. already settled).
            BWDKAuthError: If the API key is invalid.
        """
        payload = {"reason": reason, "amount": amount}
        response = self._session.post(
            self._url(f"manager/{order_uuid}/refund/"),
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        data = self._handle_response(response)
        return RefundOrderResponse.from_dict(data)

    # ------------------------------------------------------------------
    # Convenience / Workflow Helpers
    # ------------------------------------------------------------------

    def handle_callback(self, order_uuid: str, merchant_unique_id: str) -> OrderDetails:
        """
        Full callback handler: fetches order details and verifies if paid.

        Call this from your callback endpoint. It will:
          1. Fetch order details via get_order()
          2. If paid (status == 7), automatically call verify_order()
          3. Return the full OrderDetails for you to save to your DB.

        Args:
            order_uuid: From the callback URL query parameter (still verify server-side).
            merchant_unique_id: The unique ID you stored when creating the order.

        Returns:
            OrderDetails with all order information.

        Example::

            @app.route("/bwdk/callback/")
            def bwdk_callback():
                order_uuid = request.args.get("order_uuid")
                # Retrieve merchant_unique_id from your DB using order_uuid
                merchant_unique_id = db.get_unique_id(order_uuid)
                order = client.handle_callback(order_uuid, merchant_unique_id)
                if order.is_paid:
                    db.mark_order_paid(order.merchant_order_id, order.raw)
                return redirect("/order-success/")
        """
        order = self.get_order(order_uuid)

        # status 7 == PAID_BY_USER
        if order.status == 7:
            self.verify_order(order_uuid, merchant_unique_id)

        return order


# ---------------------------------------------------------------------------
# Order Status Reference
# ---------------------------------------------------------------------------

class OrderStatus:
    """Enum-like class of known order statuses."""
    WAITING_FOR_PAYMENT = 1
    WAITING_FOR_GATEWAY = 5
    PAID_BY_USER = 7
    VERIFIED_BY_MERCHANT = 9
    FAILED_TO_PAY = 6
    REFUND_COMPELETED = 17


# ---------------------------------------------------------------------------
# Quick-start example (run directly for a demo)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    API_KEY = os.environ.get("BWDK_API_KEY", "your_api_key_here")
    client = BWDKClient(api_key=API_KEY)

    items = [
        OrderItem(
            name="گوشی موبایل اپل مدل iPhone 17 Pro Max",
            primary_amount=140000,
            amount=120000,
            count=1,
            discount_amount=22500,
            tax_amount=0,
            image_link="https://example.com/img.jpg",
            options=[
                ItemOption(type_name="color", name="قرمز", value="#FF0000", is_color=True),
                ItemOption(type_name="size", name="سایز", value="xl", is_color=False),
            ],
        ),
        OrderItem(
            name="قاب سیلیکونی گوشی iPhone 17",
            primary_amount=30000,
            amount=30000,
            count=2,
            discount_amount=3750,  # per unit; total = 3750 * 2 = 7500
            tax_amount=0,
            image_link="https://example.com/img2.jpg",
            options=[
                ItemOption(type_name="other", name="جنس", value="سیلیکون", is_color=False),
            ],
        ),
    ]

    reservation = int(time.time()) + 30 * 60  # 30 minutes from now

    try:
        order = client.create_order(
            merchant_unique_id="test-unique-id-001",
            merchant_order_id="ORD-12345",
            main_amount=180000,
            final_amount=165000,
            discount_amount=30000,
            tax_amount=15000,
            callback_url="https://yourstore.com/bwdk/callback/",
            reservation_expired_at=reservation,
            items=items,
        )
        print("✅ Order created!")
        print(f"   UUID:      {order.order_uuid}")
        print(f"   Start URL: {order.order_start_url}")
    except BWDKAuthError:
        print("❌ Invalid API key.")
    except BWDKValidationError as e:
        print(f"❌ Validation error: {e}")
    except BWDKError as e:
        print(f"❌ BWDK error: {e}")