from __future__ import annotations

import json
import urllib.request
from typing import Any

from logquill.plugins.alerting_plugin import AlertingPlugin
from logquill.records import LogRecord


class SlackAlertPlugin(AlertingPlugin):
    """Sends deduplicated `AlertingPlugin` alerts to a Slack incoming webhook.

    `webhook_url` is the full "Incoming Webhook" URL from Slack's app
    config. Uses stdlib `urllib` — no extra dependency required.
    """

    def __init__(self, webhook_url: str, *, timeout: float = 5.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_alert(self, record: LogRecord, occurrences: int) -> None:
        body = json.dumps({"text": _format_message(record, occurrences)}).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status >= 400:
                raise RuntimeError(
                    f"SlackAlertPlugin: webhook returned HTTP {response.status} — "
                    "check the webhook URL is still valid in Slack's app config"
                )


def _format_message(record: LogRecord, occurrences: int) -> str:
    suffix = f" (x{occurrences})" if occurrences > 1 else ""
    return f"[{record['level']}] {record['logger']}: {record['message']}{suffix}"
