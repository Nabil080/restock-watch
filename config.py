"""Reads config.json and checks it, with error messages that say what to fix."""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

TOP_LEVEL_KEYS = {"discord_webhook", "ntfy_topic", "ntfy_server", "minutes_between_checks",
                  "browser", "headless", "locale", "products"}
PRODUCT_KEYS = {"name", "min_price", "max_price", "urls"}
URL_KEYS = {"url", "shop", "selector", "in_stock_texts", "out_of_stock_texts"}


class ConfigError(Exception):
    pass


@dataclass
class Page:
    url: str
    shop: str
    selector: str | None = None
    in_stock_texts: list[str] | None = None
    out_of_stock_texts: list[str] = field(default_factory=list)


@dataclass
class Product:
    name: str
    min_price: float
    max_price: float
    pages: list[Page]


@dataclass
class Config:
    discord_webhook: str
    ntfy_topic: str
    ntfy_server: str
    minutes_between_checks: tuple[float, float]
    browser: str
    headless: bool
    locale: str | None
    products: list[Product]


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))  # -sig: Notepad may save with a BOM
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"config.json is not valid JSON: {error.msg} at line {error.lineno}, column {error.colno}. "
            "Look for a missing comma or quote just before that spot."
        ) from None
    return parse_config(raw)


def check_keys(data: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"Unknown setting {', '.join(repr(k) for k in unknown)} {where}. "
                          f"Allowed: {', '.join(sorted(allowed))}.")


def read_price(data: dict, key: str, default: float, where: str) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ConfigError(f"{key} {where} must be a number like 549.99, without quotes or currency sign.")
    return float(value)


def shop_name(url: str) -> str:
    host = urlparse(url).hostname or url
    return host.removeprefix("www.")


def parse_page(entry, where: str) -> Page:
    if isinstance(entry, str):
        entry = {"url": entry}
    if not isinstance(entry, dict):
        raise ConfigError(f"Each entry of urls {where} must be a link in quotes, or an object with \"url\".")
    check_keys(entry, URL_KEYS, where)
    url = entry.get("url", "")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ConfigError(f"{url!r} {where} is not a web link. It should start with https://")
    for key in ("in_stock_texts", "out_of_stock_texts"):
        texts = entry.get(key, [])
        if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
            raise ConfigError(f"{key} for {url} must be a list of texts, like [\"sold out\"].")
    return Page(
        url=url,
        shop=entry.get("shop") or shop_name(url),
        selector=entry.get("selector") or None,
        in_stock_texts=entry.get("in_stock_texts") or None,
        out_of_stock_texts=entry.get("out_of_stock_texts", []),
    )


def parse_product(data, number: int) -> Product:
    if not isinstance(data, dict):
        raise ConfigError(f"Product #{number} must be an object between {{ }}.")
    name = data.get("name") or f"Product #{number}"
    where = f"in product '{name}'"
    check_keys(data, PRODUCT_KEYS, where)

    min_price = read_price(data, "min_price", 0, where)
    max_price = read_price(data, "max_price", math.inf, where)
    if min_price > max_price:
        raise ConfigError(f"min_price is above max_price {where}.")

    urls = data.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ConfigError(f"Add at least one product link to \"urls\" {where}.")
    return Product(name, min_price, max_price, [parse_page(entry, where) for entry in urls])


def parse_config(raw) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config.json must start with { and end with }.")
    check_keys(raw, TOP_LEVEL_KEYS, "in config.json")

    webhook = raw.get("discord_webhook", "")
    if webhook and not re.match(r"https://(\w+\.)?discord(app)?\.com/api/webhooks/", webhook):
        raise ConfigError("discord_webhook should look like https://discord.com/api/webhooks/...")
    topic = raw.get("ntfy_topic", "")
    if topic and not re.fullmatch(r"[\w-]{1,64}", topic):
        raise ConfigError("ntfy_topic can only use letters, digits, - and _ (64 at most).")

    minutes = raw.get("minutes_between_checks", [2, 5])
    if (not isinstance(minutes, list) or len(minutes) != 2
            or not all(isinstance(m, (int, float)) and not isinstance(m, bool) and m > 0 for m in minutes)
            or minutes[0] > minutes[1]):
        raise ConfigError("minutes_between_checks must be two numbers, shortest then longest, like [2, 5].")

    products = raw.get("products")
    if not isinstance(products, list) or not products:
        raise ConfigError("config.json has no product to watch. Add one to \"products\".")

    return Config(
        discord_webhook=webhook,
        ntfy_topic=topic,
        ntfy_server=raw.get("ntfy_server") or "https://ntfy.sh",
        minutes_between_checks=(float(minutes[0]), float(minutes[1])),
        browser=raw.get("browser", "msedge"),
        headless=bool(raw.get("headless", False)),
        locale=raw.get("locale") or None,
        products=[parse_product(product, number) for number, product in enumerate(products, start=1)],
    )
