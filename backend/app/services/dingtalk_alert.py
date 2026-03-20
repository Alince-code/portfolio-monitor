"""DingTalk custom robot notification module."""

import logging
import time
import hmac
import hashlib
import base64
import urllib.parse
from pathlib import Path
from typing import List, Optional

import requests
import yaml

logger = logging.getLogger(__name__)

# Config path
_config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"


def _load_dingtalk_config() -> dict:
    """Load DingTalk configuration from config.yaml."""
    try:
        with open(_config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("dingtalk", {})
    except Exception as e:
        logger.error(f"Failed to load DingTalk config: {e}")
        return {}


def send_dingtalk_alert(
    message: str,
    at_user_ids: Optional[List[str]] = None,
    at_mobiles: Optional[List[str]] = None,
    is_at_all: bool = False
) -> bool:
    """Send alert via DingTalk custom robot.
    
    Args:
        message: Message content to send
        at_user_ids: List of DingTalk user IDs to mention (@)
        at_mobiles: List of mobile phone numbers to mention (@)
        is_at_all: Whether to mention everyone
        
    Returns:
        bool: True if sending succeeds, False otherwise
    """
    dt_cfg = _load_dingtalk_config()
    access_token = dt_cfg.get("access_token")
    secret = dt_cfg.get("secret")

    # Merge config defaults with function arguments
    if at_user_ids is None:
        at_user_ids = dt_cfg.get("at_user_ids", [])
    if at_mobiles is None:
        at_mobiles = dt_cfg.get("at_mobiles", [])
    if not is_at_all:
        is_at_all = dt_cfg.get("is_at_all", False)

    if not access_token or not secret:
        logger.error("DingTalk config missing access_token or secret in config.yaml")
        return False

    try:
        # Generate signature according to DingTalk security rules
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        # Build URL
        url = f'https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}'

        # Build request body
        body = {
            "at": {
                "isAtAll": str(is_at_all).lower(),
                "atUserIds": at_user_ids or [],
                "atMobiles": at_mobiles or []
            },
            "text": {
                "content": message
            },
            "msgtype": "text"
        }

        headers = {'Content-Type': 'application/json'}

        logger.info(f"Sending alert to DingTalk...")
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        data = resp.json()

        if data.get("errcode") == 0:
            logger.info(f"DingTalk alert sent successfully: {message[:60]}...")
            return True
        else:
            logger.error(f"DingTalk API error: {data.get('errmsg', 'unknown')} (errcode: {data.get('errcode')})")
            logger.error(f"Full response: {data}")
            return False

    except requests.Timeout:
        logger.error("DingTalk alert send timed out (30s)")
        return False
    except Exception as e:
        logger.error(f"DingTalk alert exception: {e}")
        return False