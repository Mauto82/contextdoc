"""Shopping cart with coupon application.

Status: partially implemented.
  - Cart subtotal and basic checkout: done
  - Coupon validation before applying: TODO
  - used_count increment after checkout: TODO
"""

from dataclasses import dataclass, field
from typing import Optional

from coupon import Coupon


@dataclass
class CartItem:
    name: str
    unit_price: float
    qty: int = 1

    @property
    def total(self) -> float:
        return self.unit_price * self.qty


@dataclass
class Cart:
    items: list[CartItem] = field(default_factory=list)
    _coupon: Optional[Coupon] = field(default=None, repr=False)

    @property
    def subtotal(self) -> float:
        return sum(item.total for item in self.items)

    def add_item(self, item: CartItem) -> None:
        self.items.append(item)

    def apply_coupon(self, coupon: Coupon) -> None:
        """Attach a coupon to the cart.

        TODO: call coupon.validate(self.subtotal) before accepting the coupon.
        Currently accepts any coupon without validation.
        """
        self._coupon = coupon

    def checkout(self) -> float:
        """Return the final total after applying any coupon.

        TODO: increment coupon.used_count after a successful checkout.
        Currently the used_count is never updated.
        """
        if self._coupon is None:
            return self.subtotal
        return self._coupon.apply_discount(self.subtotal)
