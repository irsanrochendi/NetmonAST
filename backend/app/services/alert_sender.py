"""Alert notification sender: Telegram + Email."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiosmtplib
import httpx
from email.mime.text import MIMEText
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Alert, AlertNotification, AlertState

logger = logging.getLogger("alert_sender")


class TelegramSender:
    """Send alert notifications via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = self.BASE_URL.format(token=bot_token)

    async def send(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram not configured, skipping")
            return False

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                if resp.status_code == 200:
                    logger.info("Telegram notification sent")
                    return True
                else:
                    logger.warning("Telegram API error: %s %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return False


class EmailSender:
    """Send alert notifications via SMTP."""

    def __init__(self, host: str, port: int, user: str, password: str, from_email: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email

    async def send(self, to_email: str, subject: str, body: str) -> bool:
        if not self.host:
            logger.debug("SMTP not configured, skipping")
            return False

        try:
            msg = MIMEText(body, "html")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
            )
            logger.info("Email notification sent to %s", to_email)
            return True
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return False


class AlertSender:
    """Orchestrates sending alerts through all configured channels."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.telegram = TelegramSender(
            self.settings.telegram_bot_token,
            self.settings.telegram_chat_id,
        )
        self.email = EmailSender(
            self.settings.smtp_host,
            self.settings.smtp_port,
            self.settings.smtp_user,
            self.settings.smtp_password,
            self.settings.alert_from_email,
        )

    def format_telegram_message(self, alert: Alert, device_name: str) -> str:
        severity_emoji = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(
            str(alert.severity), "⚠️"
        )
        return (
            f"{severity_emoji} <b>NetMon Alert</b>\n\n"
            f"<b>{alert.message}</b>\n\n"
            f"Device: <code>{device_name}</code>\n"
            f"Severity: <code>{alert.severity}</code>\n"
            f"Time: <code>{alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>"
        )

    def format_email_body(self, alert: Alert, device_name: str) -> str:
        severity_color = {"critical": "#dc3545", "warning": "#ffc107", "info": "#17a2b8"}.get(
            str(alert.severity), "#6c757d"
        )
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="border-left: 4px solid {severity_color}; padding-left: 16px;">
                <h2 style="color: {severity_color};">⚠️ NetMon Alert</h2>
                <p><strong>{alert.message}</strong></p>
                <table style="border-collapse: collapse; margin-top: 12px;">
                    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Device:</td>
                        <td><code>{device_name}</code></td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Severity:</td>
                        <td><span style="color: {severity_color}; font-weight: bold;">{alert.severity.upper()}</span></td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Metric Value:</td>
                        <td><code>{alert.metric_value:.2f}</code></td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Threshold:</td>
                        <td><code>{alert.threshold:.2f}</code></td></tr>
                    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Time:</td>
                        <td><code>{alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</code></td></tr>
                </table>
            </div>
        </body>
        </html>
        """

    async def send_alert(self, alert: Alert, device_name: str, session: Session) -> None:
        """Send an alert through all configured channels and log results."""
        # Telegram
        tg_msg = self.format_telegram_message(alert, device_name)
        tg_ok = await self.telegram.send(tg_msg)
        self._log_notification(session, alert.id, "telegram", self.settings.telegram_chat_id, tg_ok)

        # Email (to admin users)
        from app.models import AdminUser  # avoid circular import
        admins = session.query(AdminUser).filter(AdminUser.is_active == True).all()
        for admin in admins:
            email_ok = await self.email.send(
                admin.email,
                f"[NetMon] {alert.severity.upper()}: {device_name}",
                self.format_email_body(alert, device_name),
            )
            self._log_notification(session, alert.id, "email", admin.email, email_ok)

        session.commit()

    def _log_notification(
        self, session: Session, alert_id: int, channel: str, recipient: str, success: bool
    ):
        notif = AlertNotification(
            alert_id=alert_id,
            channel=channel,
            recipient=recipient,
            status="sent" if success else "failed",
            sent_at=datetime.now(timezone.utc) if success else None,
        )
        session.add(notif)
