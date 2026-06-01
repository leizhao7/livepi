"""Environment config builders for prompt-injection tasks."""

from .base import EnvironmentConfig
from .direct_chat_txt_env import build_config as build_direct_chat_txt_env
from .email_gmail_env import build_config as build_email_gmail_env
from .shared_docs_env import build_config as build_shared_docs_env
from .slack_channel_env import build_config as build_slack_channel_env
from .telegram_group_env import build_config as build_telegram_group_env
from .whatsapp_group_env import build_config as build_whatsapp_group_env
from .web_link_env import build_config as build_web_link_env

__all__ = [
    "EnvironmentConfig",
    "build_direct_chat_txt_env",
    "build_email_gmail_env",
    "build_shared_docs_env",
    "build_slack_channel_env",
    "build_telegram_group_env",
    "build_whatsapp_group_env",
    "build_web_link_env",
]
