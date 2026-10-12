# PS5 Pro Stock Alert (PlayStation Direct NL)

Polls PlayStation Direct's product API for the PS5 Pro 2TB (`1000050720-BX`) and alerts you when it's in stock via
email, an urgent [ntfy](https://ntfy.sh) phone push, and a GitHub issue that mentions you (GitHub mobile app push).

## Run on GitHub (24/7, no laptop needed)
1. Create a Gmail App Password: https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. Create a **public** repo on github.com and push this project to it. Public repos get unlimited
   Actions minutes; a private repo's free 2,000 min/month runs out in a few days at this frequency.
   Your credentials stay private — they live in encrypted secrets, never in the code.
3. In the repo: Settings → Secrets and variables → Actions → New repository secret. Add
   `SMTP_USER` (your Gmail), `SMTP_PASSWORD` (the app password), `ALERT_TO` (where alerts go),
   and `NTFY_TOPIC` (a long random name, e.g. `ps5pro-` + `openssl rand -hex 12`).
4. Phone: install ntfy from the Play Store, tap + and subscribe to your `NTFY_TOPIC`. In the topic's
   settings, set urgent notifications to alarm / bypass Do Not Disturb if you want it loud.
5. Actions tab → "PS5 Pro stock check" → Run workflow → tick "Send a test notification". Confirm the
   email, ntfy push and GitHub issue all arrive (close the test issue afterwards).
6. Done. It runs every ~5 min (each run checks 5 times, 60s apart).

Notes:
- GitHub often delays scheduled runs by a few minutes, so expect gaps of 0–10 min.
- GitHub disables scheduled workflows after 60 days without repo activity. It emails you first;
  push any commit or click "Enable workflow" to keep it going.

## Run locally on a Mac
1. Create a Gmail App Password: https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. `cp .env.example .env` and fill in `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_TO`.
3. `python3 stock_alert.py --test` — confirm the alerts arrive.
4. `./install_launchd.sh` — checks every 60s in the background (pass a number to change the interval).

## Behaviour
- Alerts on every channel when stock flips to available, then re-alerts every 15 min by email and ntfy
  while it stays in stock (one GitHub issue per restock).
- Each channel is optional and independent: a failing one doesn't block the others.
- After 10 consecutive failed checks (e.g. the store blocks requests), sends one "checker is failing" email/ntfy alert.
- Logs: `stock_alert.log`. State: `state.json`.
- Only runs while your Mac is awake. Run `caffeinate -s` or adjust Energy settings to keep it up.

## Uninstall
`launchctl bootout gui/$(id -u)/com.ps5pro.stockalert && rm ~/Library/LaunchAgents/com.ps5pro.stockalert.plist`
