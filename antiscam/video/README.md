# 🎬 Ролики к постам antiscam

Workflow **Antiscam video** (`.github/workflows/antiscam-video.yml`) 4 раза в день берёт свежий пост канала без ролика и делает вертикальное видео 1080×1920 на 25–40 секунд:

1. **Сценарий** — Claude превращает пост в 6–8 реплик и раскладывает их по готовым сценам (`build.py`).
2. **Озвучка** — голос ElevenLabs (секреты `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`; модель Multilingual v2, stability 0.5, similarity 0.75, style 0). Без ключа — бесплатный голос Piper.
3. **Субтитры** — тайминги слов распознаются моделью GigaAM, слова подсвечиваются по ходу речи.
4. **Анимация** — Remotion, шаблон `src/scam.tsx`: телефон с перепиской, ловушка (файл, ссылка, код, звонок, карта), последствия (SMS, аккаунт, деньги, рассылка друзьям), признаки обмана, как защититься, «Подпишись».
5. **Проверка** — ролик, обложка, подпись для Instagram и текст для Threads приходят в личку (секрет `ANTISCAM_ADMIN_CHAT_ID`). Без него — только в артефактах запуска.

Настройки — раздел `video:` в `antiscam/config.yaml`: сколько роликов в день, из каких рубрик, название и соцсети в конце ролика.

Ручной запуск: **Actions → Antiscam video → Run workflow** (можно указать `post_id` из `data/antiscam_state.json` → `recent_posts`).

Сцены и сценарий: формат — `public/scenario.example.json`. Движок (`engine/`, `src/kit.tsx`, `src/frame.tsx`, `src/tl.ts`) — общий для объясняющих роликов.
