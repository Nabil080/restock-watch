"""Decides from a loaded product page whether it can be bought in the wanted price range."""

import math
import re
from dataclasses import dataclass

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
BLOCKED = "blocked"
UNKNOWN = "unknown"

# schema.org availability values that mean you can order it now. InStoreOnly is left out on purpose:
# the shop only sells it at the counter.
BUYABLE = {"InStock", "LimitedAvailability", "OnlineOnly", "PreOrder", "PreSale"}

DEFAULT_IN_STOCK_TEXTS = [
    "add to cart",
    "add to basket",
    "buy now",
    "ajouter au panier",
    "acheter maintenant",
    "in den warenkorb",
    "añadir al carrito",
    "aggiungi al carrello",
]

# Signs that the shop served an anti-bot page instead of the product.
BLOCKED_HINTS = [
    "captcha",
    "datadome",
    "are you a robot",
    "verify you are human",
    "unusual traffic",
    "access denied",
    "vérifiez que vous êtes humain",
]

CURRENCY_CODES = {"€": "EUR", "$": "USD", "£": "GBP", "eur": "EUR", "euro": "EUR", "euros": "EUR",
                  "usd": "USD", "gbp": "GBP", "chf": "CHF"}
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}

# "1 299,99", "1.299,99", "1,299.99", "549.99", "549". Thousands come in groups of 3 digits and
# cents in groups of 2, which is what tells "1,299" (thousands) from "12,99" (cents).
# Some shops split a price over several lines, hence the \s* around the separator.
NUMBER = r"(?<![\d.,])(\d{1,3}(?:[ .,'  ]\d{3})+|\d+)(?:\s*[.,]\s*(\d{2})(?!\d))?"
CURRENCY = r"(€|\$|£|euros?\b|eur\b|usd\b|gbp\b|chf\b)"
# "549,99 €", "549 EUR", and "549€99" where the cents come after the symbol.
PRICE_THEN_CURRENCY = re.compile(NUMBER + r"\s*" + CURRENCY + r"(\d{2}(?!\d))?", re.IGNORECASE)
# "$1,299.99", "£45", "€ 549".
CURRENCY_THEN_PRICE = re.compile(CURRENCY + r"\s*" + NUMBER, re.IGNORECASE)


@dataclass
class Result:
    state: str
    detail: str
    price: float | None = None
    currency: str = ""

    @property
    def price_text(self) -> str:
        return format_price(self.price, self.currency) if self.price is not None else ""


def format_price(price: float, currency: str = "") -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{price:.2f} {symbol}".strip()


def describe_range(min_price: float, max_price: float) -> str:
    if min_price > 0 and math.isfinite(max_price):
        return f"{min_price:g}-{max_price:g}"
    if math.isfinite(max_price):
        return f"at most {max_price:g}"
    if min_price > 0:
        return f"at least {min_price:g}"
    return "any price"


def _to_float(whole: str, cents: str | None) -> float:
    return float(re.sub(r"\D", "", whole) + "." + (cents or "00"))


def parse_amount(raw) -> float | None:
    """Reads a price written as a number or as text ("549.99", "549,99", "1 299,99 €")."""
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) else None
    text = str(raw).strip()
    try:
        value = float(text)
        return value if math.isfinite(value) else None
    except ValueError:
        pass
    match = re.search(NUMBER, text)
    return _to_float(*match.groups()) if match else None


def find_prices(text: str) -> list[tuple[float, str]]:
    """Finds every price written with a currency in the text. Returns (amount, currency code) pairs."""
    prices = []

    def take(match):
        whole, cents, symbol, cents_after = match.groups()
        prices.append((_to_float(whole, cents or cents_after), CURRENCY_CODES[symbol.lower()]))
        return " " * len(match.group(0))

    # Blank out what the first pattern found, so "549,99 € 12 reviews" doesn't also give "€ 12".
    text = PRICE_THEN_CURRENCY.sub(take, text)
    for match in CURRENCY_THEN_PRICE.finditer(text):
        symbol, whole, cents = match.groups()
        prices.append((_to_float(whole, cents), CURRENCY_CODES[symbol.lower()]))
    return prices


def find_phrase(text: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if phrase.lower() in text:
            return phrase
    return None


def availability_name(offer: dict) -> str:
    # "https://schema.org/InStock" -> "InStock"
    return offer["availability"].rstrip("/").rsplit("/", 1)[-1]


def judge_offers(offers: list[dict], min_price: float, max_price: float) -> Result | None:
    """Uses the schema.org offers. Returns None when they can't decide and the page text should."""
    if not offers:
        return None
    buyable = [o for o in offers if availability_name(o) in BUYABLE]
    if not buyable:
        states = ", ".join(sorted({availability_name(o) for o in offers}))
        return Result(UNAVAILABLE, f"{states} (structured data)")

    priced = []
    for offer in buyable:
        price = parse_amount(offer["price"])
        if price is not None and price > 0:
            priced.append((price, offer))
    if not priced:
        return None

    in_range = [(price, offer) for price, offer in priced if min_price <= price <= max_price]
    if in_range:
        price, offer = min(in_range, key=lambda pair: pair[0])
        seller = f", sold by {offer['seller']}" if offer["seller"] else ""
        return Result(AVAILABLE, f"{availability_name(offer)}{seller} (structured data)", price, offer["currency"])

    price, offer = min(priced, key=lambda pair: pair[0])
    result = Result(UNAVAILABLE, "", price, offer["currency"])
    result.detail = f"in stock but outside {describe_range(min_price, max_price)} (structured data)"
    return result


def judge_text(text: str, min_price: float, max_price: float,
               in_stock_texts: list[str], out_of_stock_texts: list[str]) -> Result:
    """Fallback for shops without structured data: a price in range and an add-to-cart text on the page."""
    out_of_stock = find_phrase(text, out_of_stock_texts)
    if out_of_stock:
        return Result(UNAVAILABLE, f"page says '{out_of_stock}'")

    prices = find_prices(text)
    in_range = [(price, currency) for price, currency in prices if min_price <= price <= max_price]
    cart = find_phrase(text, in_stock_texts)

    if in_range and cart:
        price, currency = min(in_range)
        return Result(AVAILABLE, f"'{cart}' on the page (page text)", price, currency)
    if not cart:
        return Result(UNAVAILABLE, "no add-to-cart button (page text)")
    if not prices:
        # A cart button but no price: probably a layout the price search doesn't know.
        return Result(UNKNOWN, "add-to-cart button but no price found (page text)")
    return Result(UNAVAILABLE, f"no price in your range ({describe_range(min_price, max_price)}) (page text)")


def judge_page(page_text: str, page_title: str, offers: list[dict], min_price: float, max_price: float,
               in_stock_texts: list[str] | None = None, out_of_stock_texts: list[str] | None = None,
               buy_box_text: str | None = None) -> Result:
    page_text = page_text.lower()
    blocked = find_phrase(page_text + " " + page_title.lower(), BLOCKED_HINTS)
    if blocked:
        return Result(BLOCKED, f"anti-bot page ('{blocked}')")
    if len(page_text) < 300:
        return Result(BLOCKED, "the page is almost empty, probably an anti-bot check")

    result = judge_offers(offers, min_price, max_price)
    if result:
        return result
    text = buy_box_text.lower() if buy_box_text else page_text
    return judge_text(text, min_price, max_price, in_stock_texts or DEFAULT_IN_STOCK_TEXTS, out_of_stock_texts or [])
