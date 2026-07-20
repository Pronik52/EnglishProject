"""Генерация картинки-сцены к фразе и её хранение на диске.

Зачем: исходная задумка приложения — ассоциативная память. Пользователь видит
изображение ситуации и запоминает фразу через образ, а не через зубрёжку.

Модуль устроен по тем же правилам, что и app/ai_generator.py:
НИКОГДА не бросает исключение наружу. При любой проблеме (нет ключа, нет сети,
таймаут, провайдер вернул мусор) возвращается None, и приложение просто
работает как раньше — с фразой без картинки.

КЛЮЧЕВОЕ РЕШЕНИЕ ПРО ДЕНЬГИ: файл именуется хешем от описания сцены, а не
привязывается к слову или пользователю. Поэтому одна и та же сцена, выпавшая
двум разным пользователям, генерируется ОДИН раз, а второй запрос попадает в
кеш на диске. Это же свойство переживёт переход на общий словарь лексем:
картинка принадлежит сцене, а не строке в таблице words.

Провайдеры (переменная окружения IMAGE_PROVIDER):
  pollinations — по умолчанию. Без ключа и без регистрации вообще.
  cloudflare   — Workers AI, FLUX-1-schnell. Бесплатная квота в сутки,
                 нужен аккаунт (карта не требуется).
  off          — генерация выключена, всегда None.
"""

from __future__ import annotations

import asyncio
import os
import base64
import hashlib
import logging
import random
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Куда складываем готовые картинки. Каталог отдаётся статикой по адресу /media
# (см. app/main.py), поэтому URL картинки — это просто /media/scenes/<файл>.
MEDIA_ROOT = Path(__file__).resolve().parent.parent / "media"
SCENES_DIR = MEDIA_ROOT / "scenes"
SCENES_URL_PREFIX = "/media/scenes"

# Размер стороны картинки. 768 — компромисс: на телефоне выглядит хорошо,
# при этом у Cloudflare расход квоты заметно ниже, чем на 1024.
IMAGE_SIZE = int(os.getenv("IMAGE_SIZE", "768"))

# Таймаут запроса к провайдеру. Он щедрый (в отличие от 15 секунд у текстовой
# генерации), потому что вызов идёт в ФОНЕ и пользователя не задерживает.
_TIMEOUT_SECONDS = float(os.getenv("IMAGE_TIMEOUT", "90"))

# Паузы перед каждой попыткой генерации, в секундах. Первая — без паузы,
# дальше ждём дольше: бесплатные тарифы ограничивают частоту запросов.
_RETRY_PAUSES = (0, 5, 15)

# Художественный стиль. Единый для всего приложения — так набор картинок
# выглядит как одна колода, а не как случайная нарезка из интернета.
_STYLE_SUFFIX = (
    "simple flat illustration, warm friendly colors, clear composition, "
    "single scene, no text, no letters, no watermark"
)


def _provider() -> str:
    return os.getenv("IMAGE_PROVIDER", "pollinations").strip().lower()


def is_enabled() -> bool:
    """Включена ли генерация картинок. Роутеры спрашивают это перед фоном."""
    return _provider() not in ("off", "none", "disabled", "")


def scene_key(scene_prompt: str) -> str:
    """Стабильный ключ сцены: хеш от текста описания + размера картинки.

    Именно он делает кеш общим для всех пользователей. Регистр и лишние
    пробелы нормализуем, чтобы «A boy eats an apple» и «a boy eats an apple»
    не порождали две разные генерации.
    """
    normalized = " ".join(scene_prompt.lower().split())
    raw = f"{normalized}|{IMAGE_SIZE}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def cached_url(scene_prompt: str) -> str | None:
    """URL уже сгенерированной картинки для этой сцены, если файл на диске."""
    if not scene_prompt:
        return None
    path = SCENES_DIR / f"{scene_key(scene_prompt)}.jpg"
    return f"{SCENES_URL_PREFIX}/{path.name}" if path.exists() else None


def _full_prompt(scene_prompt: str) -> str:
    return f"{scene_prompt.strip()}, {_STYLE_SUFFIX}"


async def _fetch_pollinations(prompt: str) -> bytes | None:
    """Pollinations.ai — бесплатно, без ключа и регистрации.

    Анонимные запросы жёстко ограничены по частоте (примерно один в 15 секунд),
    поэтому для боевого режима это не вариант — но для проверки идеи и первых
    десятков картинок подходит идеально. Токен (если завели аккаунт) поднимает
    лимит и убирает водяной знак.
    """
    url = f"https://image.pollinations.ai/prompt/{quote(_full_prompt(prompt))}"
    params = {
        "width": IMAGE_SIZE,
        "height": IMAGE_SIZE,
        "model": "flux",
        "nologo": "true",
        # Разный seed для одинаковых промптов не нужен: мы кешируем по хешу
        # промпта, поэтому seed делаем детерминированным от самого промпта.
        #
        # Берём 7 hex-символов, а не 8: восемь дают до 4294967295, а сервис
        # принимает только знаковый 32-битный int и на большие значения
        # отвечает 500. С восемью символами примерно половина сцен не
        # рисовалась бы никогда — ошибка выглядела бы как «случайные» сбои.
        "seed": int(scene_key(prompt)[:7], 16),
    }
    token = os.getenv("POLLINATIONS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        if not resp.headers.get("content-type", "").startswith("image/"):
            logger.warning("Pollinations вернул не картинку: %s", resp.headers.get("content-type"))
            return None
        return resp.content


async def _fetch_cloudflare(prompt: str) -> bytes | None:
    """Cloudflare Workers AI, модель FLUX-1-schnell.

    Бесплатная суточная квота (10 000 «нейронов») покрывает порядка тысячи
    картинок в день — этого хватает и на разработку, и на первых пользователей.
    Аккаунт нужен, карта — нет. Дальше квоты списывается по факту.
    """
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not (account_id and api_token):
        logger.warning("IMAGE_PROVIDER=cloudflare, но CLOUDFLARE_ACCOUNT_ID/"
                       "CLOUDFLARE_API_TOKEN не заданы — пропускаем картинку.")
        return None

    url = (f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
           f"/ai/run/@cf/black-forest-labs/flux-1-schnell")

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            json={"prompt": _full_prompt(prompt), "steps": 4},
        )
        resp.raise_for_status()

        # Часть моделей Workers AI отдаёт сырые байты картинки, flux-1-schnell —
        # JSON с полем result.image в base64. Поддерживаем оба варианта.
        if resp.headers.get("content-type", "").startswith("image/"):
            return resp.content

        payload = resp.json()
        if not payload.get("success", True):
            logger.warning("Cloudflare вернул ошибку: %s", payload.get("errors"))
            return None
        b64 = (payload.get("result") or {}).get("image")
        if not b64:
            logger.warning("В ответе Cloudflare нет result.image.")
            return None
        return base64.b64decode(b64)


async def generate_scene_image(scene_prompt: str) -> str | None:
    """Картинка для описания сцены: путь /media/scenes/... либо None.

    Порядок работы:
      1) если файл для этой сцены уже есть — возвращаем его, ничего не тратим;
      2) иначе идём к провайдеру и сохраняем результат на диск.

    Никогда не бросает исключение: любая ошибка логируется и даёт None.
    """
    if not scene_prompt or not scene_prompt.strip():
        return None
    if not is_enabled():
        return None

    # Шаг 1 — кеш. Самая частая ветка, когда сцены начнут повторяться.
    hit = cached_url(scene_prompt)
    if hit:
        logger.info("Картинка сцены взята из кеша: %s", hit)
        return hit

    provider = _provider()
    if provider not in ("pollinations", "cloudflare"):
        logger.warning("Неизвестный IMAGE_PROVIDER=%r — картинка не создана.", provider)
        return None
    fetch = _fetch_pollinations if provider == "pollinations" else _fetch_cloudflare

    # Повторяем при сбое. Бесплатные тарифы регулярно отвечают 500 или упираются
    # в лимит частоты, и одна случайная ошибка не должна оставлять слово без
    # картинки навсегда. Паузы растут, потому что у Pollinations анонимный лимит
    # — примерно один запрос в 15 секунд. Задача фоновая, ждать здесь не жалко.
    data = None
    for attempt, pause in enumerate(_RETRY_PAUSES):
        if pause:
            await asyncio.sleep(pause)
        try:
            data = await fetch(scene_prompt)
            if data:
                break
        except Exception as e:
            # Таймаут, сеть, 4xx/5xx, кривой JSON — всё сюда. Наружу не выпускаем.
            logger.warning("Ошибка генерации картинки (%s, попытка %d из %d): %s",
                           provider, attempt + 1, len(_RETRY_PAUSES), e)

    if not data:
        logger.warning("Картинку получить не удалось после %d попыток (%s).",
                       len(_RETRY_PAUSES), provider)
        return None

    # Шаг 2 — сохранение. Пишем во временный файл и переименовываем, чтобы
    # параллельный запрос не увидел наполовину записанную картинку.
    try:
        SCENES_DIR.mkdir(parents=True, exist_ok=True)
        final_path = SCENES_DIR / f"{scene_key(scene_prompt)}.jpg"
        tmp_path = final_path.with_suffix(f".{random.randint(1000, 9999)}.tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(final_path)
    except Exception as e:
        logger.warning("Не удалось сохранить картинку сцены: %s", e)
        return None

    url = f"{SCENES_URL_PREFIX}/{final_path.name}"
    logger.info("Сгенерирована картинка сцены (%s, %d КБ): %s",
                provider, len(data) // 1024, url)
    return url


def fallback_scene_prompt(phrase_en: str, word: str) -> str:
    """Описание сцены, когда ИИ его не дал (офлайн-фолбэк или старое слово).

    Берём саму фразу как описание — для конкретных бытовых фраз это работает
    достаточно хорошо, а качество всё равно ограничено офлайн-режимом.
    """
    base = (phrase_en or word or "").strip()
    if not base:
        return ""
    return f"An illustration of this situation: {base}"
