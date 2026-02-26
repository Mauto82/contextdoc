"""Coupon model and discount calculation logic."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DiscountType(Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


@dataclass
class Coupon:
    code: str
    discount_type: DiscountType
    discount_value: float
    max_uses: Optional[int] = None       # None = unlimited
    used_count: int = 0
    min_order_amount: Optional[float] = None
    expires_at: Optional[datetime] = None   # naive UTC datetime
    active: bool = True

    def apply_discount(self, total: float) -> float:
        """Return the discounted total. Raises ValueError if the coupon is inactive."""
        if not self.active:
            raise ValueError(f"Coupon '{self.code}' is inactive")
        if self.discount_type == DiscountType.PERCENTAGE:
            return max(0.0, total * (1 - self.discount_value / 100))
        return max(0.0, total - self.discount_value)

    def validate(self, order_total: float) -> None:
        """Raise ValueError if this coupon cannot be applied to the given order total."""
        if not self.active:
            raise ValueError(f"Coupon '{self.code}' is inactive")
        if self.max_uses is not None and self.used_count >= self.max_uses:
            raise ValueError(f"Coupon '{self.code}' has reached its usage limit")
        if self.min_order_amount is not None and order_total < self.min_order_amount:
            raise ValueError(
                f"Order total ${order_total:.2f} does not meet "
                f"minimum ${self.min_order_amount:.2f} for coupon '{self.code}'"
            )
        if self.expires_at is not None and _utcnow() > self.expires_at:
            raise ValueError(f"Coupon '{self.code}' has expired")
