#!/usr/bin/env python3
"""Check PlayStation Direct NL for PS5 Pro stock and email an alert when it's available.

Runs a single check per invocation (schedule it with launchd/cron), or loops with --loop.
Standard library only.
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
STATE_FILE = ROOT / "state.json"

PRODUCT_CODE = "1000050720-BX"  # PS5 Pro Console - 2TB (NL)
STORE_URL = "https://direct.playstation.com/nl-nl/buy-consoles/playstation5-pro-console-2-tb"
API_URL = (
    "https://api.direct.playstation.com/commercewebservices/ps-direct-nl/users/anonymous/"
    "products/productList?fields=BASIC&lang=nl_NL&productCodes=" + PRODUCT_CODE
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Origin": "https://direct.playstation.com",
    "Referer": STORE_URL,
}
# Re-send the in-stock alert at this interval while stock remains available.
REMIND_EVERY_SECONDS = 15 * 60
# Send one "checker is broken" email after this many consecutive failed checks.
ERROR_ALERT_THRESHOLD = 10


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


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
    req = urllib.request.Request(API_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    product = data["products"][0]
    status = product.get("stock", {}).get("stockLevelStatus", "unknown")
    price = product.get("price", {}).get("value")
    in_stock = (
        product.get("purchasable", False)
        and status in ("inStock", "lowStock")
    ) or product.get("maxOrderQuantity", 0) > 0
    return in_stock, status, price


def send_email(subject, body):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ.get("ALERT_TO", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    log(f"Email sent to {to}: {subject}")


def check_once():
    state = load_state()
    try:
        in_stock, status, price = fetch_stock()
    except Exception as exc:  # network errors, bot blocks, unexpected JSON
        state["failures"] = state.get("failures", 0) + 1
        log(f"Check failed ({state['failures']} in a row): {exc!r}")
        if state["failures"] >= ERROR_ALERT_THRESHOLD and not state.get("error_alerted"):
            try:
                send_email(
                    "PS5 Pro stock checker is failing",
                    f"The last {state['failures']} checks failed.\nLatest error: {exc!r}\n\n"
                    f"Check the store manually: {STORE_URL}",
                )
                state["error_alerted"] = True
            except Exception as mail_exc:
                log(f"Could not send error email: {mail_exc!r}")
        save_state(state)
        return

    state["failures"] = 0
    state["error_alerted"] = False
    log(f"Status: {status} | in stock: {in_stock} | price: €{price}")

    now = time.time()
    if in_stock and (not state["in_stock"] or now - state.get("last_alert", 0) >= REMIND_EVERY_SECONDS):
        try:
            send_email(
                "🚨 PS5 Pro IN STOCK at PlayStation Direct NL!",
                f"The PS5 Pro (2TB) is available now (status: {status}, price: €{price}).\n\n"
                f"Buy it here: {STORE_URL}\n\n"
                f"Checked at {datetime.now():%Y-%m-%d %H:%M:%S}.",
            )
            state["last_alert"] = now
        except Exception as mail_exc:
            log(f"Could not send stock email: {mail_exc!r}")
            save_state(state)  # keep in_stock False so the next run retries
            return
    state["in_stock"] = in_stock
    save_state(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="keep checking every SECONDS")
    parser.add_argument("--count", type=int, help="with --loop, stop after this many checks")
    parser.add_argument("--test-email", action="store_true", help="send a test email and exit")
    args = parser.parse_args()

    load_env()
    if args.test_email:
        send_email("PS5 Pro stock alert: test email", f"Email alerts are working.\n\n{STORE_URL}")
        return

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
