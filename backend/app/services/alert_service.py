"""Alert service — checks prices against targets and sends Telegram alerts.

Uses Telegram Bot API directly for reliability (no CLI dependency).
Supports multi-level alerts: each symbol can have a primary alert and
multiple sub-level alerts, all checked against the same real price.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import requests
import yaml
from sqlalchemy.orm import Session

from ..models import AlertSetting, AlertHistory, PriceCache

logger = logging.getLogger(__name__)

# Track last alert time per (alert_id, alert_type) to enforce cooldown
_last_alert: Dict[str, float] = {}
COOLDOWN_SECONDS = 3600  # 1 hour

# ── Load Telegram config from config.yaml ─────────────────────────────────────

_config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

# Load telegram config once at module level
def _load_telegram_config_once() -> dict:
    """Load telegram config from config.yaml (called once at import time)."""
    try:
        with open(_config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("telegram", {})
    except Exception as e:
        logger.error(f"Failed to load telegram config: {e}")
        return {}

_TELEGRAM_CONFIG = _load_telegram_config_once()


def _load_telegram_config() -> dict:
    """Return cached telegram config."""
    return _TELEGRAM_CONFIG


def _alert_key(alert_id: int, alert_type: str) -> str:
    return f"{alert_id}:{alert_type}"


def _should_alert(alert_id: int, alert_type: str) -> bool:
    """Check cooldown per alert level."""
    key = _alert_key(alert_id, alert_type)
    last = _last_alert.get(key, 0)
    return (time.time() - last) > COOLDOWN_SECONDS


def _record_alert(alert_id: int, alert_type: str):
    key = _alert_key(alert_id, alert_type)
    _last_alert[key] = time.time()


def send_telegram_alert(message: str) -> bool:
    """Send alert via Telegram Bot API to group topic 2 (💰一起发财吧)."""
    tg = _load_telegram_config()
    bot_token = tg.get("bot_token")
    chat_id = tg.get("chat_id")
    thread_id = tg.get("thread_id")

    if not bot_token or not chat_id:
        logger.error("Telegram config missing bot_token or chat_id in config.yaml")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
        }
        if thread_id:
            payload["message_thread_id"] = int(thread_id)

        logger.info(f"Sending alert to Telegram (chat={chat_id}, thread={thread_id})...")
        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()

        if data.get("ok"):
            msg_id = data.get("result", {}).get("message_id")
            logger.info(f"Alert sent to Telegram (msg_id={msg_id}): {message[:60]}...")
            return True
        else:
            logger.error(f"Telegram API error: {data.get('description', 'unknown')}")
            logger.error(f"  Full response: {data}")
            return False
    except requests.Timeout:
        logger.error("Telegram alert send timed out (30s)")
        return False
    except Exception as e:
        logger.error(f"Telegram alert exception: {e}")
        return False


def check_alerts(db: Session) -> int:
    """Check all enabled alerts against cached prices.

    Each alert (primary or sub-level) uses its own ``symbol`` field to look
    up the real market price from PriceCache. Sub-level alerts share the
    same symbol as the primary.

    Returns number of alerts triggered.
    """
    alerts = db.query(AlertSetting).filter(AlertSetting.enabled == True).all()
    triggered = 0

    now_utc = datetime.now(timezone.utc)

    for alert in alerts:
        # 过期检查（90天）
        if alert.expires_at and alert.expires_at < now_utc:
            continue

        # Look up price by symbol (always the real ticker)
        cached = db.query(PriceCache).filter(PriceCache.symbol == alert.symbol).first()
        if not cached or cached.price is None:
            continue

        price = cached.price
        symbol = alert.symbol
        name = alert.name or symbol
        label_suffix = f" [{alert.label}]" if alert.label else ""

        # Determine currency symbol based on market
        curr_sym = "¥" if getattr(alert, 'market', None) and alert.market.value == 'cn' else "$"
        amount_info = getattr(alert, 'amount', None)
        amount_line = f"交易金额: {amount_info}\n" if amount_info else ""

        # 24小时防重复：检查数据库 last_triggered_at
        from datetime import timedelta
        if alert.last_triggered_at:
            last_ts = alert.last_triggered_at
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            if (now_utc - last_ts) < timedelta(hours=24):
                continue

        alert_fired = False

        # Check target_buy (price drops to or below target)
        if alert.target_buy and price <= alert.target_buy:
            if _should_alert(alert.id, "target_buy"):
                msg = (
                    f"📉 买入信号 | {name} ({symbol}){label_suffix}\n"
                    f"当前价: {curr_sym}{price:.2f}\n"
                    f"目标买入价: {curr_sym}{alert.target_buy:.2f}\n"
                    f"{amount_line}"
                    f"已触及目标，可考虑买入！"
                )
                sent = send_telegram_alert(msg)
                _save_alert_history(db, symbol, "target_buy", msg, price, sent)
                _record_alert(alert.id, "target_buy")
                alert_fired = True
                triggered += 1

        # Check target_sell (price rises to or above target)
        if alert.target_sell and price >= alert.target_sell:
            if _should_alert(alert.id, "target_sell"):
                msg = (
                    f"📈 卖出信号 | {name} ({symbol}){label_suffix}\n"
                    f"当前价: {curr_sym}{price:.2f}\n"
                    f"目标卖出价: {curr_sym}{alert.target_sell:.2f}\n"
                    f"{amount_line}"
                    f"已触及目标，可考虑卖出！"
                )
                sent = send_telegram_alert(msg)
                _save_alert_history(db, symbol, "target_sell", msg, price, sent)
                _record_alert(alert.id, "target_sell")
                alert_fired = True
                triggered += 1

        # Check stop_loss
        if alert.stop_loss and price <= alert.stop_loss:
            if _should_alert(alert.id, "stop_loss"):
                msg = (
                    f"🚨 止损告警 | {name} ({symbol}){label_suffix}\n"
                    f"当前价: {curr_sym}{price:.2f}\n"
                    f"止损价: {curr_sym}{alert.stop_loss:.2f}\n"
                    f"{amount_line}"
                    f"⚠️ 已触及止损线，请立即关注！"
                )
                sent = send_telegram_alert(msg)
                _save_alert_history(db, symbol, "stop_loss", msg, price, sent)
                _record_alert(alert.id, "stop_loss")
                alert_fired = True
                triggered += 1

        # Check big daily change (±5%) — only for primary alerts to avoid duplicates
        if getattr(alert, 'is_primary', True) and cached.change_pct is not None and abs(cached.change_pct) >= 5.0:
            direction = "涨" if cached.change_pct > 0 else "跌"
            if _should_alert(alert.id, "big_change"):
                msg = (
                    f"⚡ 大幅波动 | {name} ({symbol})\n"
                    f"当前价: {curr_sym}{price:.2f}\n"
                    f"日{direction}幅: {cached.change_pct:+.2f}%\n"
                    f"请关注市场动态！"
                )
                sent = send_telegram_alert(msg)
                _save_alert_history(db, symbol, "big_change", msg, price, sent)
                _record_alert(alert.id, "big_change")
                alert_fired = True
                triggered += 1

        # 触发后更新 last_triggered_at
        if alert_fired:
            alert.last_triggered_at = now_utc
            db.commit()

    return triggered


def _save_alert_history(db: Session, symbol: str, alert_type: str, message: str, price: float, sent: bool):
    history = AlertHistory(
        symbol=symbol,
        alert_type=alert_type,
        message=message,
        price=price,
        triggered_at=datetime.now(timezone.utc),
        sent=sent,
    )
    db.add(history)
    db.commit()
