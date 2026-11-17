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
            return FakeResp(GOOGLE_KG)
        if "bing.com" in url:
            return FakeResp(BING_RSS)
        if "24.kg/rss" in url or "gazeta.uz/ru/rss" in url:
            return FakeResp(SITE_RSS)
        if "24.kg/proisshestvija" in url or "gazeta.uz/ru/2026" in url or "informburo.kz" in url:
            return FakeResp(ARTICLE_HTML)
        return FakeResp(b"", status=404)
    monkeypatch.setattr(bot.SESSION, "get", fake_get)


def fake_llm(system, user, key):
    """Подставной ИИ: выбирает первую новость и пишет разбор с местом по заголовку."""
    ids = re.findall(r"\[(n\d+)\]", user)
    if "Выбери до 2" in user:
        return json.dumps({"ids": ids[:1], "duplicates": []})
    if "Свежих новостей нет" in user:
        return json.dumps({"title": "Посылка, которую вы не заказывали", "intro": "Схема живучая.",
                           "how_it_works": "Ссылка на «доставку».", "red_flags": ["Срочность"],
                           "what_to_do": ["Не переходите по ссылке"], "ky": ""}, ensure_ascii=False)
    if "Texas" in user:
        loc = {"location": "США, Техас", "flag": "🇺🇸", "country_tag": "США"}
    elif "Manchester" in user:
        loc = {"location": "Великобритания, Манчестер", "flag": "🇬🇧", "country_tag": "Великобритания"}
    elif "Казпочт" in user:
        loc = {"location": "Казахстан", "flag": "🇰🇿", "country_tag": "Казахстан"}
    else:
        loc = {"location": "Кыргызстан, Бишкек", "flag": "🇰🇬", "country_tag": "Кыргызстан"}
    return json.dumps({**loc, "title": "Разбор <b>истории</b>", "what_happened": "Брали предоплату, сайт https://evil-pay.site",
                       "how_it_works": "Низкая цена и срочность.", "red_flags": ["Цена ниже рынка", "Торопят"],
                       "what_to_do": ["Звоните в банк"], "for_us": "Да, у нас похожие SMS тоже ходят.", "ky": ""},
                      ensure_ascii=False)


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
    assert by_title["FBI warns of toll road text scam targeting drivers in Texas"] == "USA"
    assert by_title["Police warn of fake parking QR code scam in Manchester"] == "WORLD"
    assert arenda[0]["category"] == "CIS" and arenda[0]["country"] == "KG"
    assert cands[0]["country"] == "KG"                                # Кыргызстан выше всех


def test_plan_order(cfg):
    assert bot.category_order(cfg, Counter())[0] == "CIS"
    assert bot.category_order(cfg, Counter({"CIS": 1}))[0] == "WORLD"
    assert bot.category_order(cfg, Counter({"CIS": 2, "WORLD": 1}))[0] == "USA"
    assert bot.category_order(cfg, Counter({"CIS": 5, "WORLD": 3, "USA": 1})) == ["USA"]
    assert bot.category_order(cfg, Counter({"CIS": 5, "WORLD": 3, "USA": 2})) == ["CIS", "WORLD", "USA"]
    assert Counter(cfg["plan"]) == Counter({"CIS": 5, "WORLD": 3, "USA": 2})


def test_full_day(cfg, fake_net, monkeypatch):
    """Прогон целого дня: квоты, жирная локация, лимит 10, напоминание, когда новости кончились."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("BOT_CTA", "🔍 Проверить ссылку: @test_bot")
    monkeypatch.setattr(bot, "call_anthropic", fake_llm)
    state = bot.load_state()
    posted = []
    for _ in range(12):
        res = bot.run_once(cfg, state)
        if not res:
            posted.append(None)
            continue
        text, preview, used, category = res
        posted.append((category, text))
        bot.mark_posted(state, used, category)

    real = [p for p in posted if p]
    cats = [c for c, _ in real]
    assert cats[0] == "CIS"
    assert "USA" in cats and "WORLD" in cats and "TIP" in cats
    assert len(real) <= cfg["daily_limit"]
    assert cats.count("TIP") == 1                                   # напоминание максимум раз в день

    for cat, text in real:
        assert text.startswith("📍 <b>")                           # место — первой строкой, жирным
        for tag in ("b", "i", "a"):
            assert text.count(f"<{tag}") == text.count(f"</{tag}>"), (tag, text)
        assert bot.visible_len(text) < 4096
        assert "@test_bot" in text and "#разбор" in text
    cis_text = next(t for c, t in real if c == "CIS")
    assert "📍 <b>🇰🇬 Кыргызстан, Бишкек</b>" in cis_text and "#СНГ" in cis_text and "#Кыргызстан" in cis_text
    assert "Разбор &lt;b&gt;истории&lt;/b&gt;" in cis_text            # HTML от ИИ экранирован
    assert "hxxps://evil-pay[.]site" in cis_text and "https://evil-pay.site" not in cis_text
    assert "Может ли это случиться у нас" not in cis_text
    us_text = next(t for c, t in real if c == "USA")
    assert "📍 <b>🇺🇸 США, Техас</b>" in us_text and "Может ли это случиться у нас" in us_text and "#США" in us_text
    tip_text = next(t for c, t in real if c == "TIP")
    assert tip_text.startswith("📍 <b>💡 Напоминание о схеме</b>")


def test_daily_limit(cfg, fake_net, monkeypatch):
    state = bot.load_state()
    day = bot.local_now().date().isoformat()
    state["posted"] = [{"url": f"u{i}", "title": f"t{i}", "ts": bot.now_utc().isoformat(), "date": day,
                        "category": "CIS", "counted": True} for i in range(10)]
    assert bot.run_once(cfg, state) is None


def test_fallback_to_other_category(cfg, fake_net, monkeypatch):
    """Если по плану США, а американских новостей нет — берём следующую рубрику."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(bot, "call_gemini", fake_llm)
    state = bot.load_state()
    day = bot.local_now().date().isoformat()
    # уже вышли 2 СНГ и 1 мир → по плану США
    state["posted"] = [{"url": f"u{i}", "title": f"x{i}", "ts": bot.now_utc().isoformat(), "date": day,
                        "category": c, "counted": True} for i, c in enumerate(["CIS", "CIS", "WORLD"])]
    # американскую новость считаем уже опубликованной
    state["posted"].append({"url": "https://news.google.com/rss/articles/AU_yqLus1?oc=5", "title": "FBI warns",
                            "ts": bot.now_utc().isoformat(), "date": day, "category": "USA", "counted": False})
    text, preview, used, category = bot.run_once(cfg, state)
    assert category in ("CIS", "WORLD")


def test_no_llm_headline(cfg, fake_net):
    text, preview, used, category = bot.run_once(cfg, bot.load_state())
    assert category == "CIS" and text.startswith("📍 <b>СНГ</b>") and "<a href=" in text


def test_state_prevents_repeat(cfg, fake_net):
    state = bot.load_state()
    cands = bot.select_candidates(bot.collect(cfg), state, cfg)
    for c in cands:
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


def test_main_dry_run(cfg, fake_net, monkeypatch, capsys):
    bot.main([])
    out = capsys.readouterr().out
    assert "тестовый режим" in out and "──────── пост" in out
    assert not os.path.exists(bot.STATE_PATH)


def test_quiet_hours(cfg, monkeypatch):
    def at(hour):
        fixed = datetime(2026, 11, 17, hour, 30, tzinfo=bot.local_tz())
        monkeypatch.setattr(bot, "local_now", lambda: fixed)
    at(12)
    assert bot.is_silent("CIS") is False and bot.is_silent("USA") is True
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
