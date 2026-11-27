import math

import pytest

from detection import AVAILABLE, BLOCKED, UNAVAILABLE, UNKNOWN, find_prices, judge_offers, judge_page, parse_amount

FILLER = " product description" * 30  # real pages are long, short ones are taken for anti-bot pages


@pytest.mark.parametrize("text, expected", [
    ("549,99 €", [(549.99, "EUR")]),
    ("549 €", [(549.0, "EUR")]),
    ("549€99", [(549.99, "EUR")]),
    ("1 299,99 €", [(1299.99, "EUR")]),
    ("1.299,99 EUR", [(1299.99, "EUR")]),
    ("$1,299.99", [(1299.99, "USD")]),
    ("£45", [(45.0, "GBP")]),
    ("12,99 €", [(12.99, "EUR")]),
    ("489\n,\n99\n€", [(489.99, "EUR")]),
    ("549,99 € 12 reviews", [(549.99, "EUR")]),
    ("549,99 euros", [(549.99, "EUR")]),
    ("no price here, 12 reviews", []),
])
def test_find_prices(text, expected):
    assert find_prices(text) == expected


@pytest.mark.parametrize("raw, expected", [
    (549.99, 549.99),
    ("549.99", 549.99),
    ("549,99", 549.99),
    ("1,299.99", 1299.99),
    ("", None),
    (math.nan, None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def offer(price, availability="https://schema.org/InStock", seller="", currency="EUR"):
    return {"price": price, "currency": currency, "availability": availability, "seller": seller}


def test_offer_in_range_is_available():
    result = judge_offers([offer("549.99")], 440, 650)
    assert result.state == AVAILABLE
    assert result.price == 549.99


def test_reseller_above_range_is_ignored():
    offers = [offer("899", seller="Reseller"), offer("549.99", "https://schema.org/OutOfStock")]
    result = judge_offers(offers, 440, 650)
    assert result.state == UNAVAILABLE
    assert "outside 440-650" in result.detail and result.price == 899


def test_cheapest_offer_in_range_wins():
    result = judge_offers([offer("620"), offer("899"), offer("549.99", seller="Shop")], 440, 650)
    assert result.price == 549.99
    assert "sold by Shop" in result.detail


def test_out_of_stock_offer():
    result = judge_offers([offer("549.99", "http://schema.org/OutOfStock")], 440, 650)
    assert result.state == UNAVAILABLE
    assert "OutOfStock" in result.detail


def test_in_store_only_is_not_buyable():
    assert judge_offers([offer("549.99", "https://schema.org/InStoreOnly")], 440, 650).state == UNAVAILABLE


def test_buyable_offer_without_price_lets_the_text_decide():
    assert judge_offers([offer("")], 440, 650) is None


def test_price_drop_mode_without_min():
    assert judge_offers([offer("189")], 0, 199).state == AVAILABLE
    assert judge_offers([offer("230")], 0, 199).state == UNAVAILABLE


def test_any_price_mode():
    assert judge_offers([offer("4999")], 0, math.inf).state == AVAILABLE


def test_page_text_fallback():
    text = "Console 549,99 € Ajouter au panier" + FILLER
    result = judge_page(text, "Shop", [], 440, 650)
    assert result.state == AVAILABLE
    assert result.price == 549.99


def test_page_text_without_cart_button():
    result = judge_page("Console 549,99 € Indisponible" + FILLER, "Shop", [], 440, 650)
    assert result.state == UNAVAILABLE


def test_page_text_out_of_stock_phrase_wins():
    text = "549,99 € Add to cart Currently unavailable" + FILLER
    result = judge_page(text, "Shop", [], 440, 650, out_of_stock_texts=["Currently unavailable"])
    assert result.state == UNAVAILABLE


def test_buy_box_is_read_instead_of_the_whole_page():
    page = "Similar items: 499,00 € Add to cart" + FILLER
    result = judge_page(page, "Shop", [], 440, 650, buy_box_text="899,00 € Add to cart")
    assert result.state == UNAVAILABLE


def test_page_without_price_or_cart_button():
    assert judge_page("Nothing to see" + FILLER, "Shop", [], 440, 650).state == UNAVAILABLE


def test_cart_button_without_price_is_unknown():
    assert judge_page("Add to cart" + FILLER, "Shop", [], 440, 650).state == UNKNOWN


def test_anti_bot_page():
    assert judge_page("Please complete the captcha" + FILLER, "Shop", [], 440, 650).state == BLOCKED
    assert judge_page("", "Shop", [], 440, 650).state == BLOCKED
