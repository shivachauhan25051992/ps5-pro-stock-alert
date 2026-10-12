# PS5 Pro Stock Alert (PlayStation Direct NL)

Polls PlayStation Direct's product API for the PS5 Pro 2TB (`1000050720-BX`) and emails you when it's in stock.

## Run on GitHub (24/7, no laptop needed)
1. Create a Gmail App Password: https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. Create a **public** repo on github.com and push this project to it. Public repos get unlimited
   Actions minutes; a private repo's free 2,000 min/month runs out in a few days at this frequency.
   Your credentials stay private — they live in encrypted secrets, never in the code.
3. In the repo: Settings → Secrets and variables → Actions → New repository secret. Add
   `SMTP_USER` (your Gmail), `SMTP_PASSWORD` (the app password), `ALERT_TO` (where alerts go).
4. Actions tab → "PS5 Pro stock check" → Run workflow → tick "Send a test email". Confirm it arrives.
5. Done. It runs every ~5 min (each run checks 5 times, 60s apart).

Notes:
- GitHub often delays scheduled runs by a few minutes, so expect gaps of 0–10 min.
- GitHub disables scheduled workflows after 60 days without repo activity. It emails you first;
  push any commit or click "Enable workflow" to keep it going.

## Run locally on a Mac
1. Create a Gmail App Password: https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. `cp .env.example .env` and fill in `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_TO`.
3. `python3 stock_alert.py --test-email` — confirm the email arrives.
4. `./install_launchd.sh` — checks every 60s in the background (pass a number to change the interval).

## Behaviour
- Alerts when stock flips to available, then re-alerts every 15 min while it stays in stock.
- After 10 consecutive failed checks (e.g. the store blocks requests), sends one "checker is failing" email.
- Logs: `stock_alert.log`. State: `state.json`.
- Only runs while your Mac is awake. Run `caffeinate -s` or adjust Energy settings to keep it up.

## Uninstall
`launchctl bootout gui/$(id -u)/com.ps5pro.stockalert && rm ~/Library/LaunchAgents/com.ps5pro.stockalert.plist`
