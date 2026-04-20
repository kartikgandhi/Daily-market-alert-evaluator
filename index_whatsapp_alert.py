#!/usr/bin/env python3
"""Send Telegram alerts when tracked Indian indices or ETFs change during the day."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Iterable
from zoneinfo import ZoneInfo

import csv
import io
import requests


NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"
NSE_QUOTE_EQUITY_URL = "https://www.nseindia.com/api/quote-equity"
NSE_HISTORICAL_INDICES_URL = "https://www.nseindia.com/api/historicalOR/indicesHistory"
NSE_HOLIDAY_MASTER_URL = "https://www.nseindia.com/api/holiday-master"
NSE_BHAVCOPY_URL_TEMPLATE = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
INDIA_TZ = ZoneInfo("Asia/Kolkata")
HOLIDAY_NOTICE_HOUR = 11
NSE_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


@dataclass(frozen=True)
class Instrument:
    name: str
    nse_key: str
    kind: str


TRACKED_INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("Nifty 50", "NIFTY 50", "index"),
    Instrument("Nifty Next 50", "NIFTY NEXT 50", "index"),
    Instrument("Nifty Smallcap 250", "NIFTY SMALLCAP 250", "index"),
    Instrument("Nifty Microcap 250", "NIFTY MICROCAP 250", "index"),
    Instrument("Nifty Midcap 150", "NIFTY MIDCAP 150", "index"),
    Instrument("Nifty IT", "NIFTY IT", "index"),
    Instrument("Nifty Bank", "NIFTY BANK", "index"),
    Instrument("HDFC Silver ETF", "HDFCSILVER", "equity"),
    Instrument("HDFC Gold ETF", "HDFCGOLD", "equity"),
)


THRESHOLDS: tuple[tuple[float, str], ...] = (
    (3.0, "Please invest in the {index} as below 3%"),
    (2.0, "Please review and invest in {index} as below 2%"),
    (1.0, "Please review the {index} is below 1%"),
)


class AlertError(Exception):
    """Raised when the alert workflow cannot complete."""


def load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AlertError(f"Missing required environment variable: {name}")
    return value


def build_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(NSE_REQUEST_HEADERS)
    return session


def fetch_index_quotes(session: requests.Session) -> dict[str, dict]:
    response = session.get(NSE_ALL_INDICES_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return {item["index"].upper(): item for item in payload.get("data", []) if item.get("index")}


def fetch_equity_quote(session: requests.Session, symbol: str) -> dict:
    response = session.get(NSE_QUOTE_EQUITY_URL, params={"symbol": symbol}, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_trading_holidays(session: requests.Session, year: int) -> dict[date, str]:
    response = session.get(
        NSE_HOLIDAY_MASTER_URL,
        params={"type": "trading", "year": year},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    holidays: dict[date, str] = {}
    for item in payload.get("CBM", []):
        raw_date = item.get("tradingDate")
        description = item.get("description")
        if not raw_date or not description:
            continue
        holidays[datetime.strptime(raw_date, "%d-%b-%Y").date()] = str(description)
    return holidays


def get_market_closed_reason(session: requests.Session, target_date: date) -> str | None:
    holidays = fetch_trading_holidays(session, target_date.year)
    if target_date in holidays:
        return holidays[target_date]
    if target_date.weekday() >= 5:
        return "Weekend"
    return None


def should_send_holiday_notice(target_date: date) -> bool:
    current_time = datetime.now(INDIA_TZ)
    return current_time.date() != target_date or current_time.hour == HOLIDAY_NOTICE_HOUR


def parse_cli_date(raw_value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    raise AlertError(
        "Invalid date format. Use YYYY-MM-DD or DD-MMM-YYYY, for example 2026-04-17."
    )


def format_nse_date(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def fetch_historical_index_percent_change(
    session: requests.Session,
    index_name: str,
    target_date: date,
) -> float | None:
    from_date = target_date - timedelta(days=10)
    response = session.get(
        NSE_HISTORICAL_INDICES_URL,
        params={
            "indexType": index_name.upper(),
            "from": format_nse_date(from_date),
            "to": format_nse_date(target_date),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    history_rows = payload.get("data", [])
    parsed_rows: list[tuple[date, float]] = []
    for row in history_rows:
        timestamp = row.get("EOD_TIMESTAMP")
        close_value = row.get("EOD_CLOSE_INDEX_VAL")
        if not timestamp or close_value is None:
            continue
        parsed_rows.append(
            (
                datetime.strptime(timestamp, "%d-%b-%Y").date(),
                float(close_value),
            )
        )

    parsed_rows.sort(key=lambda item: item[0])
    for idx, (row_date, close_value) in enumerate(parsed_rows):
        if row_date != target_date:
            continue
        if idx == 0:
            return None
        previous_close = parsed_rows[idx - 1][1]
        return ((close_value - previous_close) / previous_close) * 100

    return None


def fetch_bhavcopy_rows(session: requests.Session, target_date: date) -> dict[str, dict[str, str]]:
    formatted = target_date.strftime("%d%m%Y")
    response = session.get(NSE_BHAVCOPY_URL_TEMPLATE.format(date=formatted), timeout=30)
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))
    rows_by_symbol: dict[str, dict[str, str]] = {}
    for row in reader:
        normalized = {key.strip(): value.strip() for key, value in row.items() if key}
        symbol = normalized.get("SYMBOL")
        if symbol:
            rows_by_symbol[symbol.upper()] = normalized
    return rows_by_symbol


def resolve_alert_message(index_name: str, percent_change: float) -> str | None:
    if percent_change < 0:
        drop_percent = abs(percent_change)
        for threshold, template in THRESHOLDS:
            if drop_percent >= threshold:
                return template.format(index=index_name)

    direction = "up" if percent_change >= 0 else "down"
    return f"{index_name} is {direction} by {abs(percent_change):.2f}%"


def format_alert_line(alert: dict[str, str | float]) -> str:
    percent_change = float(alert["percent_change"])
    indicator = "🟢" if percent_change >= 0 else "🔴"
    sign = "+" if percent_change >= 0 else "-"
    return f"{alert['name']}: {indicator} {sign}{abs(percent_change):.2f}%"


def collect_live_alerts() -> list[dict[str, str | float]]:
    session = build_nse_session()
    today = datetime.now(INDIA_TZ).date()
    closed_reason = get_market_closed_reason(session, today)
    if closed_reason:
        if should_send_holiday_notice(today):
            return [
                {
                    "message_type": "market_closed",
                    "date": today.isoformat(),
                    "reason": closed_reason,
                }
            ]
        print("Market is closed today; skipping non-morning run.")
        return []

    index_quotes = fetch_index_quotes(session)
    alerts: list[dict[str, str | float]] = []
    missing_instruments: list[str] = []

    for instrument in TRACKED_INSTRUMENTS:
        percent_change: float | None = None

        if instrument.kind == "index":
            quote_item = index_quotes.get(instrument.nse_key.upper())
            if quote_item is not None:
                raw_percent = quote_item.get("percentChange")
                if raw_percent is not None:
                    percent_change = float(raw_percent)
        else:
            quote_item = fetch_equity_quote(session, instrument.nse_key)
            raw_percent = quote_item.get("priceInfo", {}).get("pChange")
            if raw_percent is not None:
                percent_change = float(raw_percent)

        if percent_change is None:
            missing_instruments.append(instrument.name)
            continue

        message = resolve_alert_message(instrument.name, percent_change)

        alerts.append(
            {
                "name": instrument.name,
                "symbol": instrument.nse_key,
                "percent_change": round(percent_change, 2),
                "message": message,
            }
        )

    if missing_instruments:
        print(
            "Warning: could not fetch live data for: "
            + ", ".join(sorted(set(missing_instruments))),
            file=sys.stderr,
        )

    return alerts


def collect_historical_alerts(target_date: date) -> list[dict[str, str | float]]:
    session = build_nse_session()
    closed_reason = get_market_closed_reason(session, target_date)
    if closed_reason:
        return [
            {
                "message_type": "market_closed",
                "date": target_date.isoformat(),
                "reason": closed_reason,
            }
        ]

    bhavcopy_rows = fetch_bhavcopy_rows(session, target_date)
    alerts: list[dict[str, str | float]] = []
    missing_instruments: list[str] = []

    for instrument in TRACKED_INSTRUMENTS:
        percent_change: float | None = None

        if instrument.kind == "index":
            percent_change = fetch_historical_index_percent_change(
                session=session,
                index_name=instrument.nse_key,
                target_date=target_date,
            )
        else:
            row = bhavcopy_rows.get(instrument.nse_key.upper())
            if row is not None:
                previous_close = row.get("PREV_CLOSE")
                close_price = row.get("CLOSE_PRICE")
                if previous_close and close_price:
                    previous_close_value = float(previous_close)
                    close_price_value = float(close_price)
                    percent_change = (
                        (close_price_value - previous_close_value) / previous_close_value
                    ) * 100

        if percent_change is None:
            missing_instruments.append(instrument.name)
            continue

        message = resolve_alert_message(instrument.name, percent_change)

        alerts.append(
            {
                "name": instrument.name,
                "symbol": instrument.nse_key,
                "percent_change": round(percent_change, 2),
                "message": message,
                "date": target_date.isoformat(),
            }
        )

    if missing_instruments:
        print(
            "Warning: could not fetch historical data for: "
            + ", ".join(sorted(set(missing_instruments))),
            file=sys.stderr,
        )

    return alerts


def build_telegram_message(alerts: Iterable[dict[str, str | float]]) -> str:
    alert_list = list(alerts)
    if not alert_list:
        return ""

    header_date = str(alert_list[0].get("date", datetime.now(INDIA_TZ).date().isoformat()))
    header_label = datetime.strptime(header_date, "%Y-%m-%d").strftime("%d-%b-%Y")
    lines = [f"Market Update for {header_label}", ""]

    first_alert = alert_list[0]
    if first_alert.get("message_type") == "market_closed":
        lines.append(f"NSE is closed today: {first_alert['reason']}.")
        return "\n".join(lines)

    for alert in alert_list:
        lines.append(format_alert_line(alert))
    return "\n".join(lines)


def send_telegram_message(alerts: Iterable[dict[str, str | float]]) -> None:
    bot_token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")
    body = build_telegram_message(alerts)

    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": body,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise AlertError(f"Telegram send failed: {payload}")

    message_id = payload.get("result", {}).get("message_id", "unknown")
    print(f"Sent Telegram market update: {message_id}", file=sys.stdout)


def main() -> int:
    load_dotenv()

    dry_run = "--dry-run" in sys.argv
    json_output = "--json" in sys.argv
    target_date: date | None = None

    if "--date" in sys.argv:
        try:
            raw_value = sys.argv[sys.argv.index("--date") + 1]
        except IndexError as exc:
            raise AlertError("Missing value after --date") from exc
        target_date = parse_cli_date(raw_value)

    try:
        alerts = collect_historical_alerts(target_date) if target_date else collect_live_alerts()
    except requests.RequestException as exc:
        raise AlertError(f"Failed to fetch market data: {exc}") from exc

    if json_output:
        print(json.dumps(alerts, indent=2))
        return 0

    if not alerts:
        if target_date:
            print(f"No Telegram message to send for {target_date.isoformat()}.")
        else:
            print("No Telegram message to send for this run.")
        return 0

    if dry_run:
        print(build_telegram_message(alerts))
        return 0

    if target_date:
        raise AlertError("Historical runs with --date are dry-run only. Add --dry-run.")

    send_telegram_message(alerts)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AlertError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
