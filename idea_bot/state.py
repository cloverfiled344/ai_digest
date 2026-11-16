"""Память бота: что уже присылали, пожелания из чата, позиция в Telegram.

Хранится в state/state.json — GitHub Actions коммитит его обратно в репозиторий,
поэтому память переживает перезапуски.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from . import config as cfg


def url_key(url: str) -> str:
    parts = urlsplit(url.strip().lower())
    host = re.sub(r"^www\.", "", parts.netloc)
    path = parts.path.rstrip("/")
    return hashlib.sha1(f"{host}{path}".encode()).hexdigest()[:16]


@dataclass
class State:
    sent: dict[str, str] = field(default_factory=dict)          # url_key → дата отправки
    recent_ideas: list[dict] = field(default_factory=list)      # [{date, title}]
    feedback: list[dict] = field(default_factory=list)          # [{date, text}]
    tg_offset: int = 0
    chat_id: int | None = None                                  # чат владельца (если не задан секретом)

    @classmethod
    def load(cls, path: str | Path = cfg.STATE_PATH) -> "State":
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: str | Path = cfg.STATE_PATH) -> None:
        self._prune()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def was_sent(self, url: str) -> bool:
        return url_key(url) in self.sent

    def mark_sent(self, urls: list[str], titles: list[str]) -> None:
        today = date.today().isoformat()
        for u in urls:
            self.sent[url_key(u)] = today
        self.recent_ideas.extend({"date": today, "title": t} for t in titles)

    def _prune(self) -> None:
        cutoff = (date.today() - timedelta(days=cfg.REMEMBER_SENT_DAYS)).isoformat()
        self.sent = {k: d for k, d in self.sent.items() if d >= cutoff}
        self.recent_ideas = self.recent_ideas[-60:]
        self.feedback = self.feedback[-cfg.MAX_FEEDBACK:]
