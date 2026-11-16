"""Отправка в Telegram и чтение пожеланий, которые ты пишешь боту."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from html import escape

import requests

from . import config as cfg
from .state import State

log = logging.getLogger(__name__)


def _quiet_hours() -> bool:
    """Ночью (до 7 утра по местному времени) сообщения приходят без звука."""
    offset = float(os.getenv("TZ_OFFSET_HOURS") or 6)
    return datetime.now(timezone(timedelta(hours=offset))).hour < 7


class Telegram:
    def __init__(self, token: str, chat_id: str | int | None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id).strip() if chat_id else None

    def _call(self, method: str, payload: dict, retries: int = 3) -> dict:
        for attempt in range(retries):
            r = requests.post(f"{self.base}/{method}", json=payload, timeout=30)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 429:
                wait = data.get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            if not data.get("ok"):
                raise TelegramError(data.get("description") or f"HTTP {r.status_code}")
            return data["result"]
        raise TelegramError("Telegram: слишком много запросов")

    def send(self, text: str, silent: bool = False) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "disable_notification": silent,
        }
        try:
            self._call("sendMessage", payload)
        except TelegramError as e:
            if "parse" not in str(e).lower():
                raise
            # сломалась разметка — отправляем тем же текстом без HTML
            log.warning("Telegram не принял HTML (%s), отправляю без разметки", e)
            payload.pop("parse_mode")
            payload["text"] = re.sub(r"<[^>]+>", "", text)
            self._call("sendMessage", payload)

    def send_all(self, messages: list[str]) -> None:
        quiet = _quiet_hours()
        for i, text in enumerate(messages):
            self.send(text, silent=quiet or i > 0)  # звенит только первое сообщение, и не ночью
            time.sleep(0.5)

    def get_updates(self, offset: int) -> list[dict]:
        payload = {"timeout": 0, "allowed_updates": ["message"]}
        if offset:
            payload["offset"] = offset + 1
        return self._call("getUpdates", payload)


class TelegramError(RuntimeError):
    pass


def sync_feedback(tg: Telegram, state: State) -> int:
    """Забирает сообщения, которые ты написал боту, и сохраняет их как пожелания.

    Telegram хранит непрочитанные сообщения ботов только 24 часа, поэтому
    workflow заглядывает сюда несколько раз в день.
    """
    added = 0
    for upd in tg.get_updates(state.tg_offset):
        state.tg_offset = max(state.tg_offset, upd["update_id"])
        msg = upd.get("message") or {}
        chat = msg.get("chat", {})
        if not tg.chat_id and chat.get("type") == "private":
            # чат не задан — привязываемся к первому, кто написал боту
            tg.chat_id, state.chat_id = str(chat["id"]), chat["id"]
            log.info("Нашёл чат владельца: %s, запоминаю", chat["id"])
        if str(chat.get("id")) != tg.chat_id:
            continue  # пишут чужие — игнорируем
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        cmd = text.split()[0].split("@")[0].lower()
        if cmd == "/start":
            tg.send("👋 Привет! Каждое утро я присылаю идеи из мира ИИ, IT и автоматизации.\n"
                    "Напиши, что тебе интереснее, и я учту это в следующих дайджестах.")
        elif cmd == "/reset":
            state.feedback = []
            tg.send("🧹 Пожелания сброшены.")
        elif cmd == "/wishes":
            if state.feedback:
                listing = "\n".join(f"• {escape(f['text'], quote=False)}" for f in state.feedback)
                tg.send(f"📝 Учитываю пожелания:\n{listing}", silent=True)
            else:
                tg.send("Пожеланий пока нет. Просто напиши, что тебе интересно.", silent=True)
        elif not text.startswith("/"):
            state.feedback.append({"date": date.today().isoformat(), "text": text[:300]})
            state.feedback = state.feedback[-cfg.MAX_FEEDBACK:]
            added += 1
    if added:
        tg.send(f"✍️ Записал пожелания ({added}). Учту в следующем дайджесте.", silent=True)
    return added
