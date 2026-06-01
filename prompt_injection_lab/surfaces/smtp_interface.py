from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SmtpConfig:
    host: str
    port: int
    secure: bool
    user: str
    password: str
    sender: str
    starttls: bool
    reject_unauthorized: bool


@dataclass
class SmtpSendResult:
    message_id: str
    recipient: str
    sender: str
    host: str
    port: int
    secure: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "recipient": self.recipient,
            "sender": self.sender,
            "host": self.host,
            "port": self.port,
            "secure": self.secure,
        }


def _prefixed_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}" if prefix else suffix


def _prefixed_env(prefix: str, suffix: str, default: str = "") -> str:
    return os.getenv(_prefixed_key(prefix, suffix), default).strip()


def _prefixed_bool(prefix: str, suffix: str, default: bool) -> bool:
    return _env_bool(_prefixed_key(prefix, suffix), default)


def smtp_config_from_env(prefix: str = "SMTP") -> SmtpConfig:
    host = _prefixed_env(prefix, "HOST")
    port_raw = _prefixed_env(prefix, "PORT", "587")
    user = _prefixed_env(prefix, "USER")
    password = _prefixed_env(prefix, "PASS")
    if prefix == "SMTP":
        password = password or os.getenv("IMAP_PASS", "").strip()
    sender = _prefixed_env(prefix, "FROM")

    if not host:
        raise RuntimeError(f"Missing {_prefixed_key(prefix, 'HOST')}")
    if not user:
        raise RuntimeError(f"Missing {_prefixed_key(prefix, 'USER')}")
    if not password:
        fallback = " (or IMAP_PASS fallback)" if prefix == "SMTP" else ""
        raise RuntimeError(f"Missing {_prefixed_key(prefix, 'PASS')}{fallback}")
    if not sender:
        raise RuntimeError(f"Missing {_prefixed_key(prefix, 'FROM')}")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid SMTP_PORT: {port_raw}") from exc

    return SmtpConfig(
        host=host,
        port=port,
        secure=_prefixed_bool(prefix, "SECURE", False),
        user=user,
        password=password,
        sender=sender,
        starttls=_prefixed_bool(prefix, "STARTTLS", True),
        reject_unauthorized=_prefixed_bool(prefix, "REJECT_UNAUTHORIZED", True),
    )


def attacker_smtp_config_from_env() -> SmtpConfig:
    attacker_keys = (
        "ATTACKER_SMTP_HOST",
        "ATTACKER_SMTP_PORT",
        "ATTACKER_SMTP_USER",
        "ATTACKER_SMTP_PASS",
        "ATTACKER_SMTP_FROM",
    )
    if any(os.getenv(key, "").strip() for key in attacker_keys):
        return smtp_config_from_env(prefix="ATTACKER_SMTP")
    return smtp_config_from_env(prefix="SMTP")


def send_smtp_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    config: SmtpConfig | None = None,
    sender_override: str | None = None,
) -> SmtpSendResult:
    cfg = config or smtp_config_from_env()
    sender = (sender_override or "").strip() or cfg.sender

    msg = EmailMessage()
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    tls_context = ssl.create_default_context()
    if not cfg.reject_unauthorized:
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE

    if cfg.secure:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=tls_context, timeout=30) as smtp:
            smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as smtp:
            smtp.ehlo()
            if cfg.starttls:
                smtp.starttls(context=tls_context)
                smtp.ehlo()
            smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)

    return SmtpSendResult(
        message_id=msg_id.strip("<>"),
        recipient=recipient,
        sender=sender,
        host=cfg.host,
        port=cfg.port,
        secure=cfg.secure,
    )
