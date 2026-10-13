# PS5 Pro Stock Alert (PlayStation Direct NL)

Polls PlayStation Direct's product API for the PS5 Pro 2TB (`1000050720-BX`) and alerts you when it's in stock with
an urgent [ntfy](https://ntfy.sh) phone push (and optionally email).

## Run on Cloudflare Workers (primary: checks every ~30s, free)
The `cloudflare/` Worker runs on a 1-minute cron and checks twice per run, then pushes to ntfy.
1. `cd cloudflare && npm install && npx wrangler login`
2. `npx wrangler kv namespace create STATE` and put the id in `wrangler.toml`.
3. Open Workers & Pages in the Cloudflare dashboard once, so it creates your workers.dev subdomain
   (cron triggers need it).
4. `printf '%s' "<your ntfy topic>" | npx wrangler secret put NTFY_TOPIC`
5. `npx wrangler deploy`, then `npx wrangler tail` to watch runs.

If no runs appear within ~15 min of the first deploy, re-register the cron by setting `crons = []`,
deploying, then restoring `crons = ["* * * * *"]` and deploying again.

## Run on GitHub (backup: every 15–35 min in practice)
1. Create a **public** repo on github.com and push this project to it. Public repos get unlimited
   Actions minutes; a private repo's free 2,000 min/month runs out in a few days at this frequency.
   Your credentials stay private — they live in encrypted secrets, never in the code.
2. In the repo: Settings → Secrets and variables → Actions → New repository secret. Add
   `NTFY_TOPIC` (a long random name, e.g. `ps5pro-` + `openssl rand -hex 12`). Optional email:
   `SMTP_USER` (your Gmail), `SMTP_PASSWORD` (a Gmail App Password from
   https://myaccount.google.com/apppasswords), `ALERT_TO` (where alerts go).
3. Phone: install ntfy from the Play Store, tap + and subscribe to your `NTFY_TOPIC`. In the topic's
   settings, enable Instant delivery, and set urgent notifications to alarm / bypass Do Not Disturb.
   In Android settings set ntfy's battery usage to Unrestricted, or alerts may only arrive when the app is open.
4. Actions tab → "PS5 Pro stock check" → Run workflow → tick "Send a test notification". Confirm it arrives.
5. Done. It's scheduled every 5 min (each run checks 5 times, 60s apart), but GitHub throttles
   scheduled runs, so real gaps are usually 15–35 min. Use it as a backup to the Cloudflare Worker.

Notes:
- GitHub disables scheduled workflows after 60 days without repo activity. It emails you first;
  push any commit or click "Enable workflow" to keep it going.

## Run locally on a Mac
1. Create a Gmail App Password: https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. `cp .env.example .env` and fill in `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_TO`.
3. `python3 stock_alert.py --test` — confirm the alerts arrive.
4. `./install_launchd.sh` — checks every 60s in the background (pass a number to change the interval).

## Behaviour
- Alerts when stock flips to available, then re-alerts every 15 min while it stays in stock.
- ntfy and email are independent: if one fails, the other still sends.
- After 10 consecutive failed checks (e.g. the store blocks requests), sends one "checker is failing" email/ntfy alert.
- Logs: `stock_alert.log`. State: `state.json`.
- Only runs while your Mac is awake. Run `caffeinate -s` or adjust Energy settings to keep it up.

## Uninstall
`launchctl bootout gui/$(id -u)/com.ps5pro.stockalert && rm ~/Library/LaunchAgents/com.ps5pro.stockalert.plist`
