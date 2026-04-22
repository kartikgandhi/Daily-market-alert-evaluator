# Telegram Index Alerts

This project checks a fixed list of Indian indices and ETFs once per run and sends a Telegram message with the market status for every tracked instrument.

The Telegram message format is intentionally short and easy to scan:

```text
Market Update for 20-Apr-2026

Nifty 50: 🟢 +0.14%
Nifty Next 50: 🔴 -0.09%
```

The alert rules behind the percentages are:

- `1%` drop: `Please review the Index is below 1%`
- `2%` drop: `Please review and invest in Index as below 2%`
- `3%` drop: `Please invest in the Index as below 3%`
- otherwise: `Index is up by ?%` or `Index is down by ?%`

The compact Telegram output always shows the instrument name, green/red status, and daily percentage change.

## Tracked instruments

- Nifty 50
- Nifty Next 50
- Nifty Smallcap 250
- Nifty Microcap 250
- Nifty Midcap 150
- Nifty IT
- Nifty Bank
- HDFC Silver ETF
- HDFC Gold ETF

## Setup

1. Create and activate a virtual environment if you want one.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your Telegram bot details.

## Telegram setup

1. In Telegram, chat with `@BotFather`.
2. Send `/newbot` and create your bot.
3. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
4. Send any message to your new bot from your Telegram account.
5. Open this URL in your browser after replacing the token:

```text
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

6. Find your numeric `chat.id` in the response and put it into `TELEGRAM_CHAT_IDS`.
7. For multiple users, use a comma-separated list like `891200356,123456789,987654321`.
8. Friends can also press `Start` on the bot; the script auto-discovers active private chats from Telegram updates.
9. New users who press `Start` receive the welcome message once: `Welcome to the stock market alerts for Mutual Funds`.
10. If someone wants to unsubscribe, they can send `/stop` to the bot.

For existing subscribers, the most reliable setup is to also add their chat IDs to the `TELEGRAM_CHAT_IDS` GitHub secret. The scheduled alert job does not send welcome messages; welcome messages are handled by the Vercel webhook described below.

## Vercel + Supabase instant onboarding

Use Vercel and Supabase when you want instant `/start` and `/stop` handling.

Vercel handles:

- instant Telegram webhook replies
- `/start` welcome message
- `/stop` unsubscribe message

Supabase stores:

- Telegram chat IDs
- username and name metadata
- active/inactive subscription state

Setup:

1. Create a Supabase project.
2. Run the SQL in `supabase/schema.sql`.
3. Deploy this repo to Vercel.
4. Add these Vercel environment variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

5. Register the Telegram webhook after Vercel deploys:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_VERCEL_DOMAIN>/api/telegram/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

6. Add these GitHub Actions secrets so scheduled alerts can read subscribers from Supabase:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Once Supabase secrets are present, the scheduled alert script reads active subscribers from Supabase. Without Supabase, it falls back to `TELEGRAM_CHAT_IDS` and Telegram update polling.

## Run

Dry run without sending messages:

```bash
python index_whatsapp_alert.py --dry-run
```

Send live Telegram alert:

```bash
python index_whatsapp_alert.py
```

JSON output for automation/debugging:

```bash
python index_whatsapp_alert.py --json
```

Historical dry-run for a specific trading date:

```bash
python index_whatsapp_alert.py --date 2026-04-17 --dry-run
```

On NSE trading holidays or weekends, the `11:00 AM` run sends a single short message and the later runs stay silent:

```text
Market Update for 14-Apr-2026

NSE is closed today: Dr. Baba Saheb Ambedkar Jayanti.
```

## macOS scheduling

Since you are on a MacBook, the recommended scheduler is `launchd`.

This project is set up to run three times each weekday in `Asia/Kolkata` time:

- `11:00 AM` to see how the market is behaving
- `2:00 PM` to make investment decisions during the day
- `3:35 PM` to see how the market ended

Install the macOS LaunchAgent:

```bash
zsh install_launch_agent.sh
```

This creates and loads a LaunchAgent in your user library:

- `~/Library/LaunchAgents/com.kartik.index-whatsapp-alerts.plist`

Useful commands:

```bash
launchctl list | grep index-whatsapp-alerts
launchctl kickstart -k gui/$(id -u)/com.kartik.index-whatsapp-alerts
zsh uninstall_launch_agent.sh
```

Logs are written to:

- `/Users/kartik/Developer/Codex/2026-04-20-build-a-program-which-send-me/logs/stdout.log`
- `/Users/kartik/Developer/Codex/2026-04-20-build-a-program-which-send-me/logs/stderr.log`

## Older cron option

I also included `install_cron.sh` if you still want cron, but on macOS the `launchd` setup is the better default.

## GitHub Actions scheduling

If your Mac may be asleep, use GitHub Actions instead of the macOS scheduler.

The workflow file is:

- `.github/workflows/market-alerts.yml`

It runs Monday to Friday at these cloud schedules:

- `10:58 AM IST`, which is `05:28 UTC`
- `1:58 PM IST`, which is `08:28 UTC`
- `3:33 PM IST`, which is `10:03 UTC`

These are each 2 minutes earlier than your original target times to give the script a little buffer.

The script also has a safety cutoff: if a scheduled run starts after `3:45 PM IST`, it skips sending the market summary. This protects against delayed cloud runs sending stale market updates after the market-close window.

In GitHub, add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`
- `SUPABASE_URL` if using Supabase subscribers
- `SUPABASE_SERVICE_ROLE_KEY` if using Supabase subscribers

`TELEGRAM_CHAT_ID` is still supported for backward compatibility, but `TELEGRAM_CHAT_IDS` is preferred for multiple subscribers.

Then push the project to GitHub. You can also test it manually from the GitHub Actions tab using `Run workflow`.

## Data source

The script now uses official NSE India JSON endpoints instead of Yahoo Finance:

- `https://www.nseindia.com/api/allIndices` for the Nifty indices
- `https://www.nseindia.com/api/quote-equity?symbol=HDFCGOLD`
- `https://www.nseindia.com/api/quote-equity?symbol=HDFCSILVER`

This is a better fit for your use case because it is the exchange source for the indexes and ETFs you asked to monitor.
