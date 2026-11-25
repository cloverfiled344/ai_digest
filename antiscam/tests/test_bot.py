"""Тесты на подставных данных: сеть, ИИ и Telegram подменяются."""
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402


def rfc(hours_ago):
    return format_datetime(datetime.now(timezone.utc) - timedelta(hours=hours_ago))


GOOGLE_KG = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>g</title>
<item><title>В Бишкеке задержали подозреваемого в мошенничестве с арендой квартир - 24.kg</title>
<link>https://news.google.com/rss/articles/CBMiK2h0dHBzOi8vMjQua2cvcHJvaXNzaGVzdHZpamEvMTIzNDU2X2FyZW5kYS_SAQA?oc=5</link>
<pubDate>{rfc(3)}</pubDate><source url="https://24.kg">24.kg</source></item>
<item><title>Курс доллара на сегодня - Sputnik</title>
<link>https://news.google.com/rss/articles/AU_yqLabc?oc=5</link><pubDate>{rfc(2)}</pubDate>
<source url="https://ru.sputnik.kg">Sputnik</source></item>
<item><title>Старая новость про мошенников - kaktus.media</title>
<link>https://news.google.com/rss/articles/AU_yqLold?oc=5</link><pubDate>{rfc(100)}</pubDate>
<source url="https://kaktus.media">kaktus.media</source></item>
</channel></rss>"""

GOOGLE_US = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>g</title>
<item><title>FBI warns of toll road text scam targeting drivers in Texas - KXAN</title>
<link>https://news.google.com/rss/articles/AU_yqLus1?oc=5</link><pubDate>{rfc(4)}</pubDate>
<source url="https://kxan.com">KXAN</source></item>
</channel></rss>"""

GOOGLE_WORLD = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>g</title>
<item><title>Police warn of fake parking QR code scam in Manchester - BBC</title>
<link>https://news.google.com/rss/articles/AU_yqLuk1?oc=5</link><pubDate>{rfc(5)}</pubDate>
<source url="https://bbc.co.uk">BBC</source></item>
</channel></rss>"""

GOOGLE_DE = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>g</title>
<item><title>Polizei warnt vor Betrug mit falschen Paketbenachrichtigungen in München - Merkur</title>
<link>https://news.google.com/rss/articles/AU_yqLde1?oc=5</link><pubDate>{rfc(6)}</pubDate>
<source url="https://merkur.de">Merkur</source></item>
</channel></rss>"""

BING_RSS = f"""<?xml version="1.0" encoding="utf-8"?><rss xmlns:News="https://www.bing.com/news/search?q=x&amp;format=rss" version="2.0"><channel><title>b</title>
<item><title>Мошенники рассылают фальшивые уведомления от Казпочты в Казахстане</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=1&amp;url=https%3a%2f%2finformburo.kz%2fnovosti%2fkazpost-fishing&amp;c=1&amp;mkt=ru-ru</link>
<description>Генпрокуратура предупредила о рассылке со ссылкой на фишинговый сайт kazpost-dostavka.site</description>
<pubDate>{rfc(5)}</pubDate><News:Source>Informburo</News:Source></item>
</channel></rss>"""

SITE_RSS = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>s</title>
<item><title>Задержан подозреваемый в мошенничестве с арендой квартир в Бишкеке</title>
<link>https://24.kg/proisshestvija/123456_arenda/</link><pubDate>{rfc(4)}</pubDate>
<description>Мужчина брал предоплату за несуществующие квартиры на Lalafo.</description></item>
<item><title>В Ташкенте раскрыли фейковый магазин в Instagram</title>
<link>https://www.gazeta.uz/ru/2026/11/16/fake-shop/</link><pubDate>{rfc(6)}</pubDate>
<description>Покупатели переводили предоплату на карты третьих лиц.</description></item>
<item><title>Погода на выходные</title><link>https://24.kg/weather/</link><pubDate>{rfc(1)}</pubDate>
<description>Солнечно</description></item>
</channel></rss>"""

ARTICLE_HTML = "<html><body><article>" + "".join(
    f"<p>Это абзац номер {i} подробного текста статьи о схеме с предоплатой и фейковым продавцом.</p>" for i in range(20)
) + "</article></body></html>"


class FakeResp:
    def __init__(self, content=b"", status=200, json_data=None):
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.status_code = status
        self._json = json_data
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.headers = {"content-type": "application/json"} if json_data is not None else {"content-type": "text/html"}
        self.text = self.content.decode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise bot.requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._json


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = bot.load_config()
    bot.CONFIG = c
    monkeypatch.setattr(bot, "STATE_PATH", str(tmp_path / "posted.json"))
    monkeypatch.setattr(bot, "LLM_ERRORS", [])
    monkeypatch.setattr(bot, "MANUAL_DIR", str(tmp_path / "manual"))
    monkeypatch.setattr(bot, "VIDEOS_PATH", str(tmp_path / "videos.json"))
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
              "CATEGORY", "DRY_RUN", "BOT_CTA", "ADD_KYRGYZ"):
        monkeypatch.delenv(k, raising=False)
    return c


@pytest.fixture
def fake_net(monkeypatch):
    def fake_get(url, timeout=0):
        if "news.google.com" in url:
            if "en-US" in url:
                return FakeResp(GOOGLE_US)
            if "en-GB" in url:
                return FakeResp(GOOGLE_WORLD)
            if "ceid=DE" in url:
                return FakeResp(GOOGLE_DE)
            if "hl=ru" in url:
                return FakeResp(GOOGLE_KG)
            return FakeResp(b"<rss><channel></channel></rss>")
        if "bing.com" in url:
            return FakeResp(BING_RSS)
        if "24.kg/rss" in url or "gazeta.uz/ru/rss" in url:
            return FakeResp(SITE_RSS)
        if "24.kg/proisshestvija" in url or "gazeta.uz/ru/2026" in url or "informburo.kz" in url:
            return FakeResp(ARTICLE_HTML)
        return FakeResp(b"", status=404)
    monkeypatch.setattr(bot.SESSION, "get", fake_get)
    # ссылки Google News раскрываются в адрес статьи (в проде — googlenewsdecoder)
    monkeypatch.setattr(bot, "resolve_google_news", lambda url, title="": "https://24.kg/proisshestvija/1")


LOCATIONS = [
    ("Texas", {"location": "США, Техас", "flag": "🇺🇸", "country_tag": "США", "scheme": "phishing"}),
    ("Manchester", {"location": "Великобритания, Манчестер", "flag": "🇬🇧", "country_tag": "Великобритания",
                    "scheme": "phishing"}),
    ("München", {"location": "Германия, Мюнхен", "flag": "🇩🇪", "country_tag": "Германия", "scheme": "#фишинг"}),
    ("Казпочт", {"location": "Казахстан", "flag": "🇰🇿", "country_tag": "Казахстан", "scheme": "phishing"}),
    ("Ташкент", {"location": "Узбекистан, Ташкент", "flag": "🇺🇿", "country_tag": "Узбекистан", "scheme": "prepayment"}),
]


def fake_llm(system, user, key):
    """Подставной ИИ: выбирает первые новости и пишет разбор с местом по тексту материала."""
    ids = re.findall(r"\[(n\d+)\]", user)
    if "Выбери до 3" in user:
        return json.dumps({"ids": ids[:3], "duplicates": []})
    if "Свежих новостей нет" in user:
        return json.dumps({"title": "Посылка, которую вы не заказывали", "intro": "Схема живучая.",
                           "how_it_works": "Ссылка на «доставку».", "red_flags": ["Срочность"],
                           "what_to_do": ["Не переходите по ссылке"], "ky": ""}, ensure_ascii=False)
    material = user.split("Материал:")[-1]
    loc = next((v for k, v in LOCATIONS if k in material),
               {"location": "Кыргызстан, Бишкек", "flag": "🇰🇬", "country_tag": "Кыргызстан", "scheme": "prepayment"})
    return json.dumps({**loc, "title": "Разбор <b>истории</b>", "what_happened": "Брали деньги, сайт https://evil-pay.site",
                       "how_it_works": "Низкая цена и срочность.", "red_flags": ["Цена ниже рынка", "Торопят"],
                       "what_to_do": ["Звоните в банк"], "for_us": "Да, у нас похожие SMS тоже ходят.", "ky": ""},
                      ensure_ascii=False)


def today_rec(i, category, **extra):
    return {"url": f"u{i}", "title": f"заглушка номер {i}", "ts": bot.now_utc().isoformat(),
            "date": bot.local_now().date().isoformat(), "category": category, "counted": True, **extra}


def test_decoders():
    assert bot.decode_bing_link(
        "http://www.bing.com/news/apiclick.aspx?ref=FexRss&url=https%3a%2f%2finformburo.kz%2fx&c=1"
    ) == "https://informburo.kz/x"
    assert bot.decode_google_link(
        "https://news.google.com/rss/articles/CBMiK2h0dHBzOi8vMjQua2cvcHJvaXNzaGVzdHZpamEvMTIzNDU2X2FyZW5kYS_SAQA?oc=5"
    ).startswith("https://24.kg/proisshestvija/123456_arenda")
    assert "news.google.com" in bot.decode_google_link("https://news.google.com/rss/articles/AU_yqLabc?oc=5")


def test_defang():
    out = bot.defang("Сайт https://kazpost-dostavka.site/pay и kaspi-bonus.online, официальный post.kz, 24.kg",
                     ["24.kg", "post.kz"])
    assert "hxxps://kazpost-dostavka[.]site/pay" in out and "kaspi-bonus[.]online" in out
    assert "post.kz" in out and "24.kg" in out


def test_collect_categories_and_dedup(cfg, fake_net):
    cands = bot.select_candidates(bot.collect(cfg), bot.load_state(), cfg)
    titles = [c["title"] for c in cands]
    assert not any("Погода" in t or "Курс доллара" in t or "Старая" in t for t in titles), titles
    arenda = [c for c in cands if "аренд" in c["title"].lower()]
    assert len(arenda) == 1 and arenda[0]["kind"] == "rss"          # дубль из Google склеен
    by_title = {c["title"]: c["category"] for c in cands}
    assert by_title["FBI warns of toll road text scam targeting drivers in Texas"] == "WORLD"   # США — часть мира
    assert by_title["Police warn of fake parking QR code scam in Manchester"] == "WORLD"
    assert by_title["Polizei warnt vor Betrug mit falschen Paketbenachrichtigungen in München"] == "WORLD"  # немецкий
    assert arenda[0]["category"] == "CIS" and arenda[0]["country"] == "KG"
    assert cands[0]["country"] == "KG"                                # Кыргызстан выше всех


def test_plan_order(cfg):
    assert Counter(cfg["plan"]) == Counter({"CIS": 2, "WORLD": 3}) and cfg["daily_limit"] == 5
    assert bot.category_order(cfg, Counter())[0] == "WORLD"
    assert bot.category_order(cfg, Counter({"WORLD": 1}))[0] == "CIS"
    assert bot.category_order(cfg, Counter({"CIS": 1, "WORLD": 1}))[0] == "WORLD"
    # СНГ не нашлось — слот СНГ остаётся первым в очереди и пробуется снова
    assert bot.category_order(cfg, Counter({"WORLD": 2})) == ["CIS", "WORLD"]


def test_legacy_usa_counts_as_world(cfg):
    state = {"posted": [today_rec(1, "USA"), today_rec(2, "CIS")], "evergreen_index": 0}
    assert bot.today_stats(state) == Counter({"WORLD": 1, "CIS": 1})


def test_full_day(cfg, fake_net, monkeypatch):
    """Прогон дня: СНГ первым, мир, рубрики-хэштеги, место жирным, напоминание не больше раза."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("BOT_CTA", "🔍 Проверить ссылку: @test_bot")
    monkeypatch.setattr(bot, "call_anthropic", fake_llm)
    state = bot.load_state()
    posted = []
    for _ in range(17):
        res = bot.run_once(cfg, state)
        if not res:
            continue
        text, preview, used, meta, category = res
        posted.append((category, text, meta))
        bot.mark_posted(state, used, category, meta)

    cats = [c for c, _, _ in posted]
    assert cats[0] == "WORLD" and "CIS" in cats and cats.count("TIP") <= 1
    assert len(posted) <= cfg["daily_limit"]
    assert cats.count("CIS") >= 2                                     # минимум 2 СНГ за день

    for cat, text, meta in posted:
        assert text.startswith("📍 <b>")
        for tag in ("b", "i", "a"):
            assert text.count(f"<{tag}") == text.count(f"</{tag}>"), (tag, text)
        assert bot.visible_len(text) < 4096 and "@test_bot" in text and "#разбор" in text
    cis_text = next(t for c, t, _ in posted if c == "CIS")
    assert "📍 <b>🇰🇬 Кыргызстан, Бишкек</b>" in cis_text and "#СНГ" in cis_text and "#Кыргызстан" in cis_text
    assert "#предоплата" in cis_text
    assert "Разбор &lt;b&gt;истории&lt;/b&gt;" in cis_text            # HTML от ИИ экранирован
    assert "hxxps://evil-pay[.]site" in cis_text and "https://evil-pay.site" not in cis_text
    assert "Может ли это случиться у нас" not in cis_text
    us_text = next(t for c, t, _ in posted if "США, Техас" in t)
    assert "📍 <b>🇺🇸 США, Техас</b>" in us_text and "Может ли это случиться у нас" in us_text
    assert "#мир" in us_text and "#США" in us_text and "#фишинг" in us_text
    de_text = next((t for c, t, _ in posted if "Германия" in t), None)
    if de_text:  # при 5 постах в день до Германии может не дойти
        assert "#фишинг" in de_text                                   # ИИ ответил хэштегом — распознан
    tip_text = next((t for c, t, _ in posted if c == "TIP"), None)
    if tip_text:
        assert tip_text.startswith("📍 <b>💡 Напоминание о схеме</b>")
    # память хранит страну и вид схемы
    countries, schemes = bot.today_mix(state)
    assert countries["США"] == 1 and schemes["phishing"] >= 2


def test_diversity_limits(cfg, fake_net, monkeypatch):
    """Если США сегодня уже было 3 раза, бот берёт следующую историю из другой страны."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    seen = []

    def llm(system, user, key):
        seen.append(user)
        if "Выбери до 3" in user:
            ids = re.findall(r"\[(n\d+)\] .*?\| (.*)", user)
            order = sorted(ids, key=lambda x: "Texas" not in x[1])   # американская история первой
            return json.dumps({"ids": [i for i, _ in order][:3], "duplicates": []})
        return fake_llm(system, user, key)

    monkeypatch.setattr(bot, "call_anthropic", llm)
    state = bot.load_state()
    state["posted"] = [today_rec(i, "WORLD", country="США", scheme="investment") for i in range(3)]
    state["posted"].append(today_rec(9, "CIS", country="Кыргызстан", scheme="prepayment"))
    monkeypatch.setenv("CATEGORY", "WORLD")
    text, preview, used, meta, category = bot.run_once(cfg, state)
    assert meta["country"] != "США" and "США, Техас" not in text
    pick_prompt = next(u for u in seen if "Выбери до 3" in u)
    assert "сша ×3" in pick_prompt and "#инвестиции ×3" in pick_prompt


def test_scheme_key(cfg):
    assert bot.scheme_key(cfg, "phishing") == "phishing"
    assert bot.scheme_key(cfg, "#звонок_из_банка") == "bank_call"
    assert bot.scheme_key(cfg, "что-то новое") == "other"


def test_daily_limit(cfg, fake_net):
    state = bot.load_state()
    state["posted"] = [today_rec(i, "WORLD") for i in range(15)]
    assert bot.run_once(cfg, state) is None


def test_fallback_when_no_cis(cfg, fake_net, monkeypatch):
    """По плану СНГ, но все истории СНГ уже вышли — публикуется мир."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(bot, "call_gemini", fake_llm)
    state = bot.load_state()
    for c in bot.select_candidates(bot.collect(cfg), state, cfg):
        if c["category"] in ("CIS", None):
            bot.mark_posted(state, bot.expand_dups([c]), "CIS")
    state["posted"] = [dict(p, date="2000-01-01") for p in state["posted"]]  # вчерашние — не в счёт плана
    text, preview, used, meta, category = bot.run_once(cfg, state)
    assert category == "WORLD"


def test_no_llm_headline(cfg, fake_net):
    text, preview, used, meta, category = bot.run_once(cfg, bot.load_state())
    assert category == "WORLD" and text.startswith("📍 <b>МИР</b>") and "<a href=" in text


def test_state_prevents_repeat(cfg, fake_net):
    state = bot.load_state()
    for c in bot.select_candidates(bot.collect(cfg), state, cfg):
        bot.mark_posted(state, bot.expand_dups([c]), c["category"] or "WORLD")
    bot.save_state(state)
    assert bot.select_candidates(bot.collect(cfg), bot.load_state(), cfg) == []


def test_send_post_fallback_and_silent(cfg, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@test")
    sent = []

    def fake_post(url, json=None, timeout=0):
        sent.append(json)
        if json.get("parse_mode") == "HTML":
            return FakeResp(status=400, json_data={"ok": False, "description": "Bad Request: can't parse entities"})
        return FakeResp(json_data={"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    assert bot.send_post("<b>Тест</b> &amp; ок", silent=True)
    assert sent[0]["disable_notification"] is True
    assert sent[1]["text"] == "Тест & ок" and "parse_mode" not in sent[1] and sent[1]["disable_notification"] is True


def test_main_dry_run(cfg, fake_net, capsys):
    bot.main([])
    out = capsys.readouterr().out
    assert "тестовый режим" in out and "──────── пост" in out
    assert not os.path.exists(bot.STATE_PATH)


def test_quiet_hours(cfg, monkeypatch):
    def at(hour):
        fixed = datetime(2026, 11, 17, hour, 30, tzinfo=bot.local_tz())
        monkeypatch.setattr(bot, "local_now", lambda: fixed)
    at(12)
    assert bot.is_silent("CIS") is False and bot.is_silent("WORLD") is False  # днём всё со звуком
    at(23)
    assert bot.is_silent("CIS") is True
    at(3)
    assert bot.is_silent("CIS") is True
    at(8)
    assert bot.is_silent("CIS") is False


def test_token_never_in_error(cfg, monkeypatch, capsys):
    secret = "1234567890:AAH_secret_token_value_should_not_leak"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@test")

    def broken_post(url, json=None, timeout=0):
        raise bot.requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(bot.requests, "post", broken_post)
    with pytest.raises(SystemExit) as exc:
        bot.send_post("<b>x</b>")
    assert secret not in str(exc.value) and secret not in capsys.readouterr().out


def test_claude_request_has_no_temperature(cfg, monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=0):
        seen.update(json)
        return FakeResp(json_data={"content": [{"type": "text", "text": "{}"}]})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    bot.call_anthropic("s", "u", "key")
    assert "temperature" not in seen and seen["model"] == "claude-haiku-5-5"


def test_run_fails_loudly_when_ai_errors(cfg, fake_net, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)

    def broken(system, user, key):
        raise ValueError("model rejected request")

    monkeypatch.setattr(bot, "call_anthropic", broken)
    with pytest.raises(SystemExit) as exc:
        bot.main([])
    assert "ИИ не ответил" in str(exc.value)


def test_send_post_falls_back_to_saved_chat(cfg, monkeypatch):
    """Секрет указывает на старый @адрес канала — бот шлёт в запомненный chat_id и запоминает его."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@old_name")
    sent = []

    def fake_post(url, json=None, timeout=0):
        sent.append(json["chat_id"])
        if json["chat_id"] == "@old_name":
            return FakeResp(status=400, json_data={"ok": False, "description": "Bad Request: chat not found"})
        return FakeResp(json_data={"ok": True, "result": {"message_id": 9, "chat": {"id": -100555}}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    state = {"chat_id": -100555}
    assert bot.send_post("<b>Тест</b>", state=state)
    assert sent == ["@old_name", "-100555"] and state["chat_id"] == -100555


def test_send_post_discovers_single_channel(cfg, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@old_name")

    def fake_post(url, json=None, timeout=0):
        if url.endswith("/getUpdates"):
            return FakeResp(json_data={"ok": True, "result": [
                {"channel_post": {"chat": {"id": -100777, "type": "channel", "title": "Канал"}}}]})
        if json["chat_id"] == "-100777":
            return FakeResp(json_data={"ok": True, "result": {"message_id": 1, "chat": {"id": -100777}}})
        return FakeResp(status=400, json_data={"ok": False, "description": "Bad Request: chat not found"})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    state = {}
    assert bot.send_post("Тест", state=state) and state["chat_id"] == -100777


def test_due_count_and_slots(cfg):
    tz = bot.local_tz()
    at = lambda h, m=0: datetime(2026, 11, 19, h, m, tzinfo=tz)  # noqa: E731
    assert bot.due_count(cfg, at(7, 0)) == 0       # ночью постов нет
    assert bot.due_count(cfg, at(9, 20)) == 1
    assert bot.due_count(cfg, at(16, 0)) == 3
    assert bot.due_count(cfg, at(23, 0)) == 5
    assert bot.recent_due(cfg, at(16, 0)) == 1     # за 3 часа прошёл только слот 15:17
    assert bot.seconds_to_next_slot(cfg, at(9, 0)) == 17 * 60
    assert bot.seconds_to_next_slot(cfg, at(22, 0)) == (11 * 60 + 17) * 60  # следующий — 9:17 завтра


def _run_loop(cfg, monkeypatch, start, minutes, state=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@chan")
    monkeypatch.setenv("LOOP_MINUTES", str(minutes))
    monkeypatch.setattr(bot, "call_anthropic", fake_llm)
    bot.CONFIG = cfg
    clock = {"t": start}
    monkeypatch.setattr(bot, "local_now", lambda: clock["t"])
    real = {"t": 0.0}
    monkeypatch.setattr(bot.time, "time", lambda: real["t"])

    def fake_sleep(sec):
        real["t"] += sec
        clock["t"] += timedelta(seconds=sec)

    monkeypatch.setattr(bot.time, "sleep", fake_sleep)
    sent = []
    monkeypatch.setattr(bot, "send_post", lambda text, preview=None, silent=False, state=None:
                        sent.append((clock["t"], text)) or True)
    bot.loop(dry=False)
    return sent


def test_loop_posts_on_slots_and_skips_stale(cfg, fake_net, monkeypatch):
    """Запуск в 13:00, за день ничего не вышло: ночные и 9:17 не догоняются, выходит 12:17, потом 15:17."""
    tz = bot.local_tz()
    sent = _run_loop(cfg, monkeypatch, datetime(2026, 11, 19, 13, 0, tzinfo=tz), 300)
    times = [t.strftime("%H:%M") for t, _ in sent]
    assert times == ["13:00", "15:17", "18:17"] or times[:2] == ["13:00", "15:17"]


def test_manual_post_goes_first_once(cfg, fake_net, monkeypatch, tmp_path):
    os.makedirs(bot.MANUAL_DIR)
    with open(os.path.join(bot.MANUAL_DIR, "001.yaml"), "w", encoding="utf-8") as f:
        f.write('title: "Это ты на видео?"\nlocation: "Telegram"\nscheme: hacking\nhow_it_works: "Шаги"\n'
                'red_flags: ["Файл .apk"]\nwhat_to_do: ["Не открывать"]\n')
    tz = bot.local_tz()
    sent = _run_loop(cfg, monkeypatch, datetime(2026, 11, 19, 9, 20, tzinfo=tz), 200)
    assert "Это ты на видео?" in sent[0][1] and "#взлом" in sent[0][1]
    assert sum("Это ты на видео?" in t for _, t in sent) == 1
    assert bot.load_state()["manual_done"] == ["001.yaml"]


def test_video_approval_publishes_reply(cfg, monkeypatch):
    """Админ нажал «Опубликовать» — ролик уходит в канал ответом на исходный пост."""
    bot.CONFIG = dict(cfg, video={"admin_chat_id": "42"})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100555")
    bot.save_videos({"p1": {"status": "pending", "file_id": "FILE", "caption": "<b>Пост</b> целиком", "replace": 77},
                     "p2": {"status": "pending", "file_id": "F2", "caption": "x"}})
    calls = []

    def fake_post(url, json=None, timeout=0):
        method = url.rsplit("/", 1)[-1]
        calls.append((method, json))
        if method == "getUpdates":
            return FakeResp(json_data={"ok": True, "result": [
                {"update_id": 10, "callback_query": {"id": "c1", "from": {"id": 999}, "data": "vpub:p2"}},   # чужой
                {"update_id": 11, "callback_query": {"id": "c2", "from": {"id": 42}, "data": "vpub:p1",
                                                     "message": {"chat": {"id": 42}, "message_id": 5}}},
                {"update_id": 12, "callback_query": {"id": "c3", "from": {"id": 42}, "data": "vskip:p2"}}]})
        if method == "sendVideo":
            return FakeResp(json_data={"ok": True, "result": {"message_id": 88}})
        return FakeResp(json_data={"ok": True, "result": True})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    state = {}
    assert bot.poll_approvals(state)
    v = bot.load_videos()
    assert v["p1"]["status"] == "published" and v["p1"]["channel_message_id"] == 88
    assert v["p2"]["status"] == "skipped" and state["tg_offset"] == 13
    sv = next(j for m, j in calls if m == "sendVideo")
    assert sv["video"] == "FILE" and "reply_parameters" not in sv and sv["chat_id"] == "-100555" and sv["parse_mode"] == "HTML"
    dm = next(j for m, j in calls if m == "deleteMessage")
    assert dm["message_id"] == 77                                     # исходный текстовый пост заменён роликом


def test_thin_story_skipped(cfg, fake_net, monkeypatch):
    """Статью не удалось прочитать — пустой пост «подробностей нет» не публикуется."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(bot, "call_anthropic", fake_llm)
    monkeypatch.setattr(bot, "fetch_article_text", lambda url, limit=3500, title="": "")
    bot.CONFIG = cfg
    cands = [{"id": "n1", "title": "Новая уловка мошенников", "summary": "", "link": "https://x.kg/1",
              "category": "CIS", "norm": "новая уловка", "source": "x"}]
    monkeypatch.setattr(bot, "llm_pick", lambda *a, **k: (cands, []))
    assert bot.make_story(cfg, cands, "CIS") is None
