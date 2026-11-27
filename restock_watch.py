"""Watches product pages and sends an alert when one can be bought in your price range.

    python restock_watch.py           watch until stopped (Ctrl+C or close the window)
    python restock_watch.py --test    check every page once, print what was found, send a test message
"""

import argparse
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page as Tab
from playwright.sync_api import sync_playwright

from config import Config, ConfigError, Page, Product, load_config
from detection import UNKNOWN, Result, describe_range, format_price, judge_page
from notify import Notifier
from tracker import BLOCKED_WARNING_AFTER, Event, PageTracker

if getattr(sys, "frozen", False):
    # Packaged .exe: config.json sits next to the exe, bundled files are unpacked to a temp folder.
    APP_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).parent
    BUNDLE_DIR = APP_DIR

CONFIG_PATH = APP_DIR / "config.json"
EXAMPLE_PATH = BUNDLE_DIR / "config.example.json"
PROFILE_DIR = APP_DIR / "browser_profile"  # cookies kept between runs, so a captcha solved once stays solved
EXTRACT_OFFERS_JS = (BUNDLE_DIR / "extract_offers.js").read_text(encoding="utf-8")

PAGE_TIMEOUT_MS = 45_000
SETTLE_MS = 4_000  # many shops fill in the price and run their anti-bot check after the page loads

LABELS = {"available": "AVAILABLE", "unavailable": "not now", "blocked": "BLOCKED", "unknown": "unknown"}


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def create_config() -> None:
    shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)
    log(f"Created {CONFIG_PATH}")
    log("Put your product links and your Discord webhook or ntfy topic in it, save, then start again.")
    if getattr(sys, "frozen", False):
        subprocess.Popen(["notepad.exe", str(CONFIG_PATH)])


def read_page(tab: Tab, product: Product, page: Page) -> Result:
    try:
        tab.goto(page.url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        tab.wait_for_timeout(SETTLE_MS)
        text = tab.locator("body").inner_text()
        offers = tab.evaluate(EXTRACT_OFFERS_JS)
        buy_box = None
        if page.selector and tab.locator(page.selector).count() > 0:
            buy_box = tab.locator(page.selector).first.inner_text()
        title = tab.title()
    except PlaywrightError as error:
        return Result(UNKNOWN, f"page did not load: {str(error).splitlines()[0]}")
    return judge_page(text, title, offers, product.min_price, product.max_price,
                      page.in_stock_texts, page.out_of_stock_texts, buy_box)


def status_line(product: Product, page: Page, result: Result) -> str:
    price = f"{result.price_text}, " if result.price is not None else ""
    return f"{LABELS[result.state]:<11} {product.name} @ {page.shop}: {price}{result.detail}"


def send_event(notifier: Notifier, event: Event, product: Product, page: Page, result: Result) -> None:
    if event.kind == "available":
        title = f"{product.name} is available on {page.shop}"
        message = f"{result.price_text} (your range: {describe_range(product.min_price, product.max_price)})"
        notifier.alert(title, message, page.url)
    elif event.kind == "cheaper":
        title = f"{product.name} dropped to {result.price_text} on {page.shop}"
        message = f"Was {format_price(event.old_price, result.currency)} at the last alert."
        notifier.alert(title, message, page.url)
    elif event.kind == "blocked":
        notifier.info(
            f"{page.shop} has shown an anti-bot page {BLOCKED_WARNING_AFTER} times in a row ({product.name}). "
            "Solve the check by hand in the browser window, the bot keeps the cookie."
        )


def open_tabs(context: BrowserContext, count: int) -> list[Tab]:
    tabs = list(context.pages)
    while len(tabs) < count:
        tabs.append(context.new_page())
    return tabs


def watch(config: Config, notifier: Notifier, test: bool) -> None:
    watched = [(product, page) for product in config.products for page in product.pages]
    trackers = [PageTracker() for _ in watched]

    with sync_playwright() as playwright:
        # One tab per page, kept open: if a shop asks for a captcha, it can be solved in its tab.
        context = playwright.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel=config.browser or None,
            headless=config.headless,
            locale=config.locale,
            viewport={"width": 1280, "height": 900},
        )
        tabs = open_tabs(context, len(watched))
        try:
            if test:
                lines = []
                for tab, (product, page) in zip(tabs, watched):
                    line = status_line(product, page, read_page(tab, product, page))
                    log(line)
                    lines.append(line)
                if notifier.enabled:
                    notifier.info("restock-watch test, no alert sent:\n" + "\n".join(lines))
                    log("Test message sent.")
                return

            watching = f"{plural(len(watched), 'page')} for {plural(len(config.products), 'product')}"
            log(f"Watching {watching}. Ctrl+C to stop.")
            notifier.info(f"restock-watch started, watching {watching}.")
            while True:
                for i, (product, page) in enumerate(watched):
                    if tabs[i].is_closed():
                        tabs[i] = context.new_page()
                    result = read_page(tabs[i], product, page)
                    log(status_line(product, page, result))
                    event = trackers[i].update(result)
                    if event:
                        send_event(notifier, event, product, page, result)
                        log(f"Sent the '{event.kind}' message for {product.name} @ {page.shop}")

                wait = random.uniform(*config.minutes_between_checks) * 60
                log(f"Next check at {datetime.now() + timedelta(seconds=wait):%H:%M}")
                time.sleep(wait)
        finally:
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sends an alert when a product is back in stock in your price range.")
    parser.add_argument("--test", action="store_true", help="check every page once and send a test message")
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        create_config()
        return 1
    try:
        config = load_config(CONFIG_PATH)
    except ConfigError as error:
        log(f"Problem in config.json: {error}")
        return 1

    notifier = Notifier(config.discord_webhook, config.ntfy_topic, config.ntfy_server, log)
    if not notifier.enabled:
        log("No discord_webhook or ntfy_topic in config.json: alerts will only show here.")

    try:
        watch(config, notifier, args.test)
    except KeyboardInterrupt:
        log("Stopped.")
    except Exception as error:
        log(f"Error: {error}")
        notifier.info(f"restock-watch stopped because of an error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    # Prices and shop names can hold characters a non-UTF-8 console can't print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    code = main()
    if getattr(sys, "frozen", False):
        # Launched by double-click: keep the window open so the last messages can be read.
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    sys.exit(code)
