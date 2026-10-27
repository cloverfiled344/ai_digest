# 🤖 AI-дайджест в Telegram

Каждое утро (около 9:00 по Бишкеку) бот присылает подборку самого полезного про AI за сутки:
новые модели и релизы, инструменты для кода, свежие репозитории на GitHub, видео с YouTube,
статьи дня с Hugging Face, обсуждения на Hacker News, Хабр. Отбор делает Claude по твоему
профилю интересов: хайп, кликбейт и повторы выкидываются, к каждому пункту — 1–2 строки на русском,
что это и зачем.

Работает бесплатно на GitHub Actions: компьютер включённым держать не нужно.

## Что внутри

| Файл | Зачем |
|---|---|
| `digest.py` | сам бот: собирает → отбирает через Claude → отправляет |
| `profile.md` | **что тебе интересно** — Claude отбирает по этому тексту, правь как хочешь |
| `sources.yaml` | источники: RSS, YouTube-каналы, Hacker News, GitHub, HF Papers |
| `.github/workflows/digest.yml` | расписание запуска |
| `data/state.json` | появится сам: что уже отправлено, чтобы не повторяться |

## Настройка (≈10 минут)

### 1. Создай бота в Telegram
1. Открой [@BotFather](https://t.me/BotFather) → `/newbot` → придумай имя и username (должен заканчиваться на `bot`).
2. BotFather пришлёт **токен** вида `1234567890:AAH...` — сохрани его.
3. Открой своего нового бота и нажми **Start** (иначе он не сможет тебе писать).

### 2. Получи ключ Claude API
1. Зайди на [console.anthropic.com](https://console.anthropic.com) → **API Keys** → **Create Key**.
2. Пополни баланс в разделе Billing.

Сколько стоит: на модели Sonnet 5.5 (по умолчанию) один дайджест — примерно 5 центов,
то есть около $1.5–2 в месяц. Можно переключиться на Haiku 5.5 — она примерно в 20 раз дешевле,
но отбирает чуть грубее (см. «Настройки» ниже).

### 3. Создай репозиторий на GitHub
1. [github.com/new](https://github.com/new) → имя, например `ai-digest`, → **Private** → Create.
2. **Add file → Upload files** → перетащи `digest.py`, `profile.md`, `sources.yaml`, `requirements.txt`, `README.md` → Commit.
3. Файл расписания: **Add file → Create new file** → в имени файла напиши
   `.github/workflows/digest.yml` (слэши сами создадут папки) → вставь содержимое файла `digest.yml` → Commit.

### 4. Добавь секреты
**Settings → Secrets and variables → Actions → New repository secret**, по одному:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `ANTHROPIC_API_KEY` | ключ Claude API |
| `TELEGRAM_CHAT_ID` | пока пропусти — узнаем на следующем шаге |

### 5. Узнай свой chat_id и запусти
1. Вкладка **Actions** → слева **AI digest** → **Run workflow**.
2. Первый запуск упадёт (красный крестик) — это нормально. Открой его → шаг *Build and send digest*,
   там будет строка `TELEGRAM_CHAT_ID = 123456789`.
3. Добавь этот номер секретом `TELEGRAM_CHAT_ID`.
4. Снова **Run workflow** — через минуту-две дайджест придёт в Telegram. 🎉

Дальше бот работает сам каждый день.

## Настройки

- **Что присылать** — редактируй `profile.md` прямо на GitHub (иконка ✏️). Пиши обычным языком:
  «больше про локальные модели», «не нужно про картинки и видеогенерацию» и т.п.
- **Источники** — `sources.yaml`: добавляй любые RSS, YouTube-каналы (`"@handle"`), темы GitHub.
- **Количество пунктов** — `max_items` в `sources.yaml`.
- **Время** — строка `cron` в `.github/workflows/digest.yml`. Время там в UTC: Бишкек = UTC+6,
  то есть `"47 2 * * *"` → 8:47. Для 20:00 по Бишкеку будет `"0 14 * * *"`.
- **Модель** — Settings → Secrets and variables → Actions → вкладка **Variables** → New variable
  `CLAUDE_MODEL` = `claude-haiku-5-5` (дешевле) или `claude-opus-5-5` (умнее и дороже).
- **Без Claude** — если не задать `ANTHROPIC_API_KEY`, бот пришлёт простой топ по рейтингу без отбора и пояснений.

## Если что-то не работает

- Открой последний запуск во вкладке **Actions**: по каждому источнику там видно ✓ или ✗ с причиной.
  Один сломанный источник не ломает дайджест — он просто пропускается.
- `Telegram: Forbidden` — ты не нажал Start у бота, или chat_id неверный.
- `Claude API 401` — неверный ключ; `Claude API 400 ... credit` — закончился баланс.
- Ошибка на шаге *Save state* (`Permission denied`) — Settings → Actions → General →
  Workflow permissions → **Read and write permissions** → Save.
- Reddit часто блокирует серверы GitHub — для этого источника ✗ это нормально.

## Запуск на своём компьютере (необязательно)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ANTHROPIC_API_KEY=...
python digest.py --dry-run   # посмотреть дайджест в консоли, ничего не отправляя
python digest.py             # собрать и отправить
```
