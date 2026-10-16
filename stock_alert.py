#!/usr/bin/env python3
"""Check the PlayStation NL store for PS5 Pro stock and alert (ntfy and/or email) when it's available.

Runs a single check per invocation (schedule it with launchd/cron), or loops with --loop.
Standard library only.
"""
import argparse
import gzip
import json
import os
import smtplib
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
STATE_FILE = ROOT / "state.json"
# GitHub runners use UTC; show times as they are in the Netherlands.
TIMEZONE = ZoneInfo("Europe/Amsterdam")

# PlayStation Direct NL moved to playstation.com in Oct 2026, and the old stock API now returns 403.
# The new product page embeds the live stock status in its server-rendered data.
PRODUCT_ID = "PSD001-PSDE01942_39-PS5PROCHASASIRSE"  # PS5 Pro Console - 2TB (NL)
STORE_URL = "https://www.playstation.com/nl-nl/ps5/ps5-pro/buy-now/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
}
STATUS_RE = re.compile(r'"stockLevelStatus":"([A-Z_]+)"')
PRICE_RE = re.compile(r'"price":"([0-9.]+)","priceCurrency":"EUR"')
# Re-send the in-stock alert at this interval while stock remains available.
REMIND_EVERY_SECONDS = 15 * 60
# Send one "checker is broken" email after this many consecutive failed checks.
ERROR_ALERT_THRESHOLD = 10


def log(msg):
    print(f"[{datetime.now(TIMEZONE).isoformat(timespec='seconds')}] {msg}", flush=True)


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {"in_stock": False, "last_alert": 0, "failures": 0, "error_alerted": False}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_stock():
    """Return (in_stock, status, price) for the product."""
    req = urllib.request.Request(STORE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        final_url = resp.geturl()
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    # Sony puts a virtual waiting room in front of the store during drops.
    if "queue" in final_url.split("/")[2]:
        return True, "QUEUE", None
    page = raw.decode("utf-8", "replace").replace('\\"', '"')
    if PRODUCT_ID not in page:
        raise ValueError(f"PS5 Pro product data not found on {final_url}")
    statuses = set(STATUS_RE.findall(page))
    if not statuses:
        raise ValueError("No stock status found on the product page")
    price = PRICE_RE.search(page)
    in_stock = statuses != {"OUT_OF_STOCK"}
    return in_stock, "/".join(sorted(statuses)), price.group(1) if price else None


def send_email(subject, body):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ.get("ALERT_TO") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    log(f"Email sent to {to}: {subject}")


def send_ntfy(subject, body, urgent):
    """Push to the ntfy Android app (https://ntfy.sh)."""
    server = os.environ.get("NTFY_SERVER") or "https://ntfy.sh"
    req = urllib.request.Request(
        f"{server.rstrip('/')}/{os.environ['NTFY_TOPIC']}",
        data=body.encode(),
        headers={
            # HTTP headers must be latin-1; ntfy renders the emoji tag instead.
            "Title": subject.encode("ascii", "ignore").decode().strip(),
            "Priority": "urgent" if urgent else "default",
            "Tags": "rotating_light" if urgent else "warning",
            "Click": STORE_URL,
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).close()
    log(f"ntfy push sent: {subject}")


def notify(subject, body, urgent=True):
    """Send through every configured channel. Returns True if at least one succeeded."""
    channels = []
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        channels.append(("email", lambda: send_email(subject, body)))
    if os.environ.get("NTFY_TOPIC"):
        channels.append(("ntfy", lambda: send_ntfy(subject, body, urgent)))
    if not channels:
        log("No notification channels configured")
        return False

    sent = False
    for name, send in channels:
        try:
            send()
            sent = True
        except Exception as exc:
            log(f"Could not send {name} notification: {exc!r}")
    return sent


def check_once():
    state = load_state()
    try:
        in_stock, status, price = fetch_stock()
    except Exception as exc:  # network errors, bot blocks, unexpected JSON
        state["failures"] = state.get("failures", 0) + 1
        log(f"Check failed ({state['failures']} in a row): {exc!r}")
        if state["failures"] >= ERROR_ALERT_THRESHOLD and not state.get("error_alerted"):
            state["error_alerted"] = notify(
                "PS5 Pro stock checker is failing",
                f"The last {state['failures']} checks failed.\nLatest error: {exc!r}\n\n"
                f"Check the store manually: {STORE_URL}",
                urgent=False,
            )
        save_state(state)
        return

    state["failures"] = 0
    state["error_alerted"] = False
    log(f"Status: {status} | in stock: {in_stock} | price: €{price}")

    now = time.time()
    if in_stock and (not state["in_stock"] or now - state.get("last_alert", 0) >= REMIND_EVERY_SECONDS):
        if status == "QUEUE":
            title = "🚨 PS5 Pro: PlayStation store queue is open!"
            headline = "PlayStation's waiting-room queue is active, so a drop is likely starting. Join it now."
        else:
            title = "🚨 PS5 Pro IN STOCK at PlayStation Direct NL!"
            headline = f"The PS5 Pro (2TB) is available now (status: {status}, price: €{price})."
        sent = notify(
            title,
            f"{headline}\n\nBuy it here: {STORE_URL}\n\n"
            f"Checked at {datetime.now(TIMEZONE):%Y-%m-%d %H:%M:%S %Z}.",
        )
        if not sent:
            save_state(state)  # keep in_stock False so the next run retries
            return
        state["last_alert"] = now
    state["in_stock"] = in_stock
    save_state(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="keep checking every SECONDS")
    parser.add_argument("--count", type=int, help="with --loop, stop after this many checks")
    parser.add_argument("--test", "--test-email", action="store_true",
                        help="send a test notification through every configured channel and exit")
    args = parser.parse_args()

    load_env()
    if args.test:
        ok = notify("PS5 Pro stock alert: test notification",
                    f"Notifications are working.\n\n{STORE_URL}")
        return 0 if ok else 1

    if args.loop:
        checks = 0
        while True:
            check_once()
            checks += 1
            if args.count and checks >= args.count:
                break
            time.sleep(args.loop)
    else:
        check_once()


if __name__ == "__main__":
    sys.exit(main())
