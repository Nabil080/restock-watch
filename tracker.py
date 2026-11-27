"""Remembers what each page showed last time, so an alert goes out once per restock and not every round."""

from dataclasses import dataclass

from detection import AVAILABLE, BLOCKED, UNAVAILABLE, Result

BLOCKED_WARNING_AFTER = 5  # blocked checks in a row before warning the user


@dataclass
class Event:
    kind: str  # "available", "cheaper" or "blocked"
    old_price: float | None = None


@dataclass
class PageTracker:
    available: bool = False
    alerted_price: float | None = None
    blocked_in_a_row: int = 0

    def update(self, result: Result) -> Event | None:
        """Takes the latest check of the page and returns the alert to send, if any."""
        if result.state == BLOCKED:
            self.blocked_in_a_row += 1
            if self.blocked_in_a_row == BLOCKED_WARNING_AFTER:
                return Event("blocked")
            return None
        self.blocked_in_a_row = 0

        if result.state == UNAVAILABLE:
            self.available = False
            self.alerted_price = None
            return None

        if result.state == AVAILABLE:
            if not self.available:
                self.available = True
                self.alerted_price = result.price
                return Event("available")
            if result.price is not None and self.alerted_price is not None and result.price < self.alerted_price - 0.005:
                old_price = self.alerted_price
                self.alerted_price = result.price
                return Event("cheaper", old_price)

        # An unknown result (page didn't load, no price) keeps the last known state, so a flaky
        # page doesn't send the same alert again on the next good check.
        return None
