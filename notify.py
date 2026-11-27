"""Sends messages to a Discord webhook and to an ntfy topic."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable

USER_AGENT = "restock-watch"


def post_json(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=15):
        pass


class Notifier:
    def __init__(self, discord_webhook: str, ntfy_topic: str, ntfy_server: str, log: Callable[[str], None]):
        self.discord_webhook = discord_webhook
        self.ntfy_topic = ntfy_topic
        self.ntfy_server = ntfy_server.rstrip("/")
        self.log = log

    @property
    def enabled(self) -> bool:
        return bool(self.discord_webhook or self.ntfy_topic)

    def alert(self, title: str, message: str, url: str) -> None:
        """An alert worth waking up for: pings @everyone on Discord, high priority on ntfy."""
        # The bare link makes Discord show the shop's preview, with the product picture.
        content = f"@everyone **{title}**\n{message}\n{url}"
        self._send_discord({"content": content[:2000], "allowed_mentions": {"parse": ["everyone"]}})
        self._send_ntfy({"title": title, "message": message, "priority": 4, "click": url, "tags": ["shopping_cart"]})

    def info(self, message: str) -> None:
        """A status message, without ping."""
        self._send_discord({"content": message[:2000], "allowed_mentions": {"parse": []}})
        self._send_ntfy({"message": message[:4000], "priority": 3})

    def _send_discord(self, payload: dict) -> None:
        if not self.discord_webhook:
            return
        try:
            post_json(self.discord_webhook, payload)
        except urllib.error.HTTPError as error:
            hint = " Check discord_webhook in config.json." if error.code in (401, 403, 404) else ""
            self.log(f"Discord refused the message (HTTP {error.code}).{hint}")
        except (urllib.error.URLError, TimeoutError) as error:
            self.log(f"Could not reach Discord: {error}")

    def _send_ntfy(self, payload: dict) -> None:
        if not self.ntfy_topic:
            return
        try:
            post_json(self.ntfy_server, {"topic": self.ntfy_topic, **payload})
        except urllib.error.HTTPError as error:
            self.log(f"ntfy refused the message (HTTP {error.code}).")
        except (urllib.error.URLError, TimeoutError) as error:
            self.log(f"Could not reach ntfy: {error}")
