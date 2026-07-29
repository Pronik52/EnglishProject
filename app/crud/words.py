from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..database import SessionLocal
from ..phrases import generate_phrase, generate_variants, get_phrase
from ..ai_generator import ai_generate_phrase
from ..translator import translate_to_ru
from ..image_generator import (
    cached_url,
    fallback_scene_prompt,
    generate_scene_image,
    is_enabled as images_enabled,
)
from ..evaluator import PASS_GRADE, evaluate_description

logger = logging.getLogger(__name__)


class DuplicateWordError(Exception):
    """Слово с таким же переводом уже есть в словаре пользователя.

    Появилась вместе с уникальным ключом словаря. Раньше ограничения не было,
    и одно и то же слово можно было завести дважды; теперь ручное добавление
    отвечает понятной ошибкой вместо падения на констрейнте базы.
    """


def find_duplicate(db: Session, owner_id: int, text: str, translation: str):
    """Существующее слово с тем же значением или None.

    Английское слово отсеиваем в SQL, а русский перевод сравниваем уже в
    Python. Причина: lower() в SQLite работает только с латиницей и оставляет
    «Яблоко» как есть, поэтому сравнение кириллицы средствами базы дало бы
    разный результат на SQLite и PostgreSQL. Латиница таким свойством не
    страдает, так что сужение выборки по text корректно на обеих базах.
    """
    target_text = (text or "").strip().lower()
    target_translation = (translation or "").strip().lower()

    candidates = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        func.lower(models.Word.text) == target_text,
    ).all()

    for candidate in candidates:
        if (candidate.translation or "").strip().lower() == target_translation:
            return candidate
    return None

# --- Лимиты ---
# Это защита от злоупотреблений, а не тариф. Каждое добавленное слово и каждая
# проверка описания — вызов внешнего API за деньги, и открытая ручка без потолка
# выносится одним скриптом. Пороги подобраны так, чтобы обычный человек их не
# замечал: 50 слов в день — это уже больше, чем реально можно выучить.
#
# Раньше здесь стояли 10/5/20, и они работали как пейволл: упереться в них
# получалось на первом же занятии, после чего открывалась форма оплаты.
def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


# Сколько слов в сутки можно добавить. Premium — без лимита.
DAILY_WORD_LIMIT = _int_env("DAILY_WORD_LIMIT", 50)

# Сколько раз можно перегенерировать фразу для ОДНОГО слова.
REGEN_LIMIT = _int_env("REGEN_LIMIT", 10)

# Сколько описаний картинки в сутки проверяет ИИ. Единственный режим, который
# ходит в LLM на каждый ответ, поэтому потолок здесь нужен в первую очередь.
DAILY_DESCRIBE_LIMIT = _int_env("DAILY_DESCRIBE_LIMIT", 50)

# --- SRS (интервальные повторы, система Лейтнера) ---
SRS_MAX_LEVEL = 5
# Дней до следующего повтора после достижения уровня (индекс = уровень).
# Уровень 0 (новое слово или ошибка) — повтор сразу.
SRS_INTERVALS_DAYS = [0, 1, 3, 7, 14, 30]


# Условие «слово пора повторить»: невыученное, срок повтора наступил или не
# задан. Живёт отдельной функцией, потому что по нему считается и число на
# дашборде (get_words_stats), и состав учебной сессии (crud/study.py). Пока
# правило было записано дважды, эти две цифры могли разъехаться.
def due_filter(now: datetime = None):
    now = now or datetime.utcnow()
    return (
        models.Word.is_learned == False,  # noqa: E712 — SQLAlchemy требует ==
        (models.Word.due_at == None) | (models.Word.due_at <= now),  # noqa: E711
    )


# Пересчитывает SRS слова по результату повтора: верно → уровень выше и интервал
# больше; ошибка → сброс на 0 и повтор сразу. is_learned — по достижении максимума.
def _apply_srs(word: models.Word, correct: bool):
    if correct:
        word.srs_level = min((word.srs_level or 0) + 1, SRS_MAX_LEVEL)
    else:
        word.srs_level = 0
    word.due_at = datetime.utcnow() + timedelta(days=SRS_INTERVALS_DAYS[word.srs_level])
    word.is_learned = word.srs_level >= SRS_MAX_LEVEL
    word.review_count = (word.review_count or 0) + 1


# Записывает ответ в журнал повторов. Вызывается из всех режимов ответа,
# чтобы история была полной — по ней потом строятся статистика и графики.
# Саму запись не коммитим: это делает вызывающая функция вместе с изменением
# слова, иначе журнал и прогресс могли бы разъехаться при ошибке.
def _log_review(db: Session, word: models.Word, mode: str, correct: bool,
                grade: int, answer_text: str = None) -> None:
    db.add(models.ReviewLog(
        user_id=word.owner_id,
        word_id=word.id,
        mode=mode,
        correct=correct,
        grade=grade,
        answer_text=answer_text,
        srs_level_after=word.srs_level or 0,
    ))


# Сколько описаний картинки пользователь проверил за текущие сутки (UTC).
def count_describes_today(db: Session, user_id: int) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(models.ReviewLog).filter(
        models.ReviewLog.user_id == user_id,
        models.ReviewLog.mode == "describe",
        models.ReviewLog.created_at >= start
    ).count()


# Обнуляет счётчики генераций фразы у всех слов пользователя.
# Вызывается при возврате с Premium на Free — чтобы снова были доступны 5 генераций.
def reset_regens(db: Session, owner_id: int) -> None:
    db.query(models.Word).filter(
        models.Word.owner_id == owner_id
    ).update({models.Word.regen_count: 0})
    db.commit()


# Сколько слов пользователь добавил за текущие сутки (UTC).
def count_words_created_today(db: Session, owner_id: int) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        models.Word.created_at >= start
    ).count()

# Создаёт слово для конкретного владельца.
# owner_id передаём отдельно — он берётся из токена, а не из схемы.
# Бэкенд сразу генерирует короткую фразу с этим словом для запоминания.
async def create_word(db: Session, word: schemas.WordCreate, owner_id: int, level: str = "A1"):
    # Фраза и её перевод формируются вместе (ИИ, с офлайн-фолбэком) и сразу
    # сохраняются в базу — чтобы перевод хранился с момента создания слова.
    data = await get_phrase(word.text, word.translation, level=level)
    scene = data.get("scene_prompt") or ""

    # Картинку в этом запросе НЕ рисуем — она занимает секунды и заставила бы
    # пользователя ждать. Исключение: если такая сцена уже кому-то выпадала,
    # файл лежит на диске и достаётся мгновенно, бесплатно и без фона.
    image_url = cached_url(scene) if scene else None
    image_status = _initial_image_status(scene, image_url)

    # Слово можно завести сразу выученным (например, при импорте уже знакомой
    # лексики). Тогда синхронизируем SRS так же, как это делает toggle_learned:
    # максимальный уровень и дальний повтор, иначе слово тут же вернулось бы
    # в тренировку, несмотря на отметку.
    is_learned = bool(getattr(word, "is_learned", False))
    srs_level = SRS_MAX_LEVEL if is_learned else 0
    due_at = datetime.utcnow() + timedelta(
        days=SRS_INTERVALS_DAYS[SRS_MAX_LEVEL] if is_learned else 0
    )

    db_word = models.Word(
        text=word.text,
        translation=word.translation,
        phrase=data["phrase_en"],
        phrase_ru=data["phrase_ru"],
        scene_prompt=scene,
        image_url=image_url,
        image_status=image_status,
        is_learned=is_learned,
        srs_level=srs_level,
        due_at=due_at,  # новое слово сразу «к повтору», выученное — нескоро
        owner_id=owner_id
    )
    if find_duplicate(db, owner_id, word.text, word.translation):
        raise DuplicateWordError(word.text)

    db.add(db_word)
    try:
        db.commit()
    except IntegrityError:
        # Проверка выше могла разойтись с реальностью, если два одинаковых
        # запроса пришли одновременно. Уникальный ключ ловит это в любом случае.
        db.rollback()
        raise DuplicateWordError(word.text)
    db.refresh(db_word)
    return db_word


# Каким должен быть image_status у только что созданной/обновлённой фразы:
# ready — картинка уже нашлась в кеше, pending — её пойдёт рисовать фон,
# none — рисовать нечего или генерация выключена в настройках.
def _initial_image_status(scene: str, image_url: str | None) -> str:
    if image_url:
        return "ready"
    if scene and images_enabled():
        return "pending"
    return "none"


# Фоновая дорисовка картинки к слову. Запускается через BackgroundTasks уже
# ПОСЛЕ того, как ответ ушёл пользователю, поэтому работает со своей сессией:
# сессия запроса к этому моменту закрыта.
#
# Никогда не бросает исключение — иначе упадёт фоновый воркер FastAPI, а для
# пользователя это всего лишь отсутствующая картинка.
async def generate_word_image(word_id: int, owner_id: int) -> None:
    db = SessionLocal()
    try:
        word = get_word(db, word_id=word_id, owner_id=owner_id)
        if word is None or not word.scene_prompt:
            return

        url = await generate_scene_image(word.scene_prompt)

        # Перечитываем слово: пока рисовалась картинка, его могли удалить.
        word = get_word(db, word_id=word_id, owner_id=owner_id)
        if word is None:
            return

        word.image_url = url
        word.image_status = "ready" if url else "failed"
        db.commit()
    except Exception:
        logger.exception("Фоновая генерация картинки для слова %s не удалась", word_id)
    finally:
        db.close()


# Свежая случайная фраза для слова + её русский перевод. Сначала ИИ (даёт разный
# результат каждый раз), при недоступности — оффлайн-варианты. Не повторяем текущую.
async def _fresh_phrase(word: str, translation: str, level: str, avoid: str):
    ai = await ai_generate_phrase(word, translation, level, avoid=avoid)
    if ai and ai["phrase_en"] and ai["phrase_en"] != avoid:
        en = ai["phrase_en"]
        scene = ai.get("scene_prompt") or fallback_scene_prompt(en, word)
        return en, (ai["phrase_ru"] or translate_to_ru(en)), scene
    # Фолбэк: детерминированные варианты, берём отличный от текущего.
    variants = generate_variants(word, translation, level=level, count=3)
    en = next((v for v in variants if v != avoid), variants[0])
    return en, translate_to_ru(en), fallback_scene_prompt(en, word)


# Лениво возвращает русский перевод фразы слова, кешируя его в phrase_ru.
# None — слова нет/чужое; "" — перевод недоступен (офлайн), но слово найдено.
def get_phrase_translation(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None
    if word.phrase_ru:
        return word.phrase_ru
    ru = translate_to_ru(word.phrase or "")
    if ru:
        word.phrase_ru = ru
        db.commit()
    return ru


# Генерирует новую фразу для существующего слова (кнопка "другая фраза").
# Возвращает кортеж (status, word):
#   "not_found" — слова нет / чужое;
#   "limit"     — бесплатный лимит генераций по этому слову исчерпан;
#   "ok"        — фраза обновлена.
async def regenerate_phrase(db: Session, word_id: int, owner_id: int,
                            level: str = "A1", is_premium: bool = False):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return "not_found", None

    if not is_premium and (word.regen_count or 0) >= REGEN_LIMIT:
        return "limit", word

    word.phrase, word.phrase_ru, word.scene_prompt = await _fresh_phrase(
        word.text, word.translation, level, avoid=word.phrase
    )
    # Фраза сменилась — старая картинка ей больше не соответствует. Если новая
    # сцена уже есть в кеше, подставляем сразу; иначе её дорисует фон.
    word.image_url = cached_url(word.scene_prompt) if word.scene_prompt else None
    word.image_status = _initial_image_status(word.scene_prompt, word.image_url)
    word.regen_count = (word.regen_count or 0) + 1
    db.commit()
    db.refresh(word)
    return "ok", word


# Возвращает слова конкретного пользователя с пагинацией и фильтрацией.
def get_words_by_owner(
    db: Session,
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    is_learned: bool = None
):
    query = db.query(models.Word).filter(models.Word.owner_id == owner_id)

    if search:
        query = query.filter(
            models.Word.text.ilike(f"%{search}%") |
            models.Word.translation.ilike(f"%{search}%")
        )

    if is_learned is not None:
        query = query.filter(models.Word.is_learned == is_learned)

    total = query.count()
    words = query.offset(skip).limit(limit).all()

    return {"items": words, "total": total}


# Возвращает ОДНО слово по id, но только если оно принадлежит этому владельцу.
# Двойной фильтр (id + owner_id) защищает от доступа к чужим словам.
def get_word(db: Session, word_id: int, owner_id: int):
    return db.query(models.Word).filter(
        models.Word.id == word_id,
        models.Word.owner_id == owner_id
    ).first()


# Удаляет слово (только своё). Возвращает True если удалили, False если не нашли.
def delete_word(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id, owner_id)
    if word is None:
        return False
    db.delete(word)
    db.commit()
    return True

import random


# «Повторить» из списка = успешный повтор: продвигаем слово по SRS вверх.
def review_word(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    _apply_srs(word, correct=True)
    _log_review(db, word, mode="review", correct=True, grade=3)
    db.commit()
    db.refresh(word)
    return word


# Ответ в режиме викторины: верно → повышаем SRS-уровень и интервал,
# неверно → сброс на 0 и повтор сразу.
def answer_word(db: Session, word_id: int, owner_id: int, correct: bool,
                mode: str = "choice", answer_text: str = None):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    _apply_srs(word, correct=correct)
    _log_review(db, word, mode=mode, correct=correct,
                grade=3 if correct else 0, answer_text=answer_text)
    db.commit()
    db.refresh(word)
    return word


# Готовит сцену для слова, у которого её ещё нет.
#
# Нужна для слов, заведённых до появления картинок: у них есть фраза, но нет
# ни scene_prompt, ни изображения. Описание сцены выводим из самой фразы —
# это бесплатно и мгновенно, лишний вызов ИИ не нужен.
#
# Возвращает (status, word):
#   "not_found" — слова нет / чужое;
#   "disabled"  — генерация картинок выключена настройкой;
#   "no_phrase" — у слова нет даже фразы, рисовать нечего;
#   "pending"   — картинку пошёл рисовать фон;
#   "ready"     — картинка уже есть (нашлась в кеше или была раньше).
def ensure_scene(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return "not_found", None
    if word.image_url:
        return "ready", word
    if word.image_status == "pending":
        return "pending", word
    if not images_enabled():
        return "disabled", word

    if not word.scene_prompt:
        word.scene_prompt = fallback_scene_prompt(word.phrase or "", word.text)
    if not word.scene_prompt:
        return "no_phrase", word

    word.image_url = cached_url(word.scene_prompt)
    word.image_status = _initial_image_status(word.scene_prompt, word.image_url)
    db.commit()
    db.refresh(word)
    return ("ready" if word.image_url else "pending"), word


# Главный режим: пользователь описал картинку своими словами.
# Возвращает кортеж (status, word, verdict):
#   "not_found" — слова нет / чужое;
#   "no_scene"  — к слову нет картинки, описывать нечего;
#   "limit"     — исчерпан дневной лимит проверок на бесплатном тарифе;
#   "ok"        — ответ разобран, verdict содержит оценку и подсказки.
#
# Оценка мягкая: повтор засчитывается за уместное употребление слова и
# переданный смысл сцены. Замечания по грамматике попадают в verdict и
# показываются пользователю, но на SRS не влияют.
async def describe_word(db: Session, word_id: int, owner_id: int, answer: str,
                        level: str = "A1", is_premium: bool = False):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return "not_found", None, None

    if not word.scene_prompt:
        return "no_scene", word, None

    if not is_premium and count_describes_today(db, owner_id) >= DAILY_DESCRIBE_LIMIT:
        return "limit", word, None

    verdict = await evaluate_description(
        word=word.text,
        translation=word.translation,
        phrase=word.phrase or "",
        scene=word.scene_prompt,
        level=level,
        answer=answer,
    )

    correct = verdict["grade"] >= PASS_GRADE
    _apply_srs(word, correct=correct)
    _log_review(db, word, mode="describe", correct=correct,
                grade=verdict["grade"], answer_text=answer)
    db.commit()
    db.refresh(word)
    return "ok", word, verdict


# Сбрасывает прогресс по слову: SRS-уровень на 0, снимает "выучено",
# слово снова "к повтору" — учить с нуля.
def reset_reviews(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    word.srs_level = 0
    word.review_count = 0
    word.is_learned = False
    word.due_at = datetime.utcnow()
    db.commit()
    db.refresh(word)
    return word


# Вручную переключает is_learned. Синхронизируем SRS: выучено → максимальный
# уровень и дальний повтор; вернуть в учёбу → уровень 0 и повтор сразу.
def toggle_learned(db: Session, word_id: int, owner_id: int, is_learned: bool):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    word.is_learned = is_learned
    if is_learned:
        word.srs_level = SRS_MAX_LEVEL
        word.due_at = datetime.utcnow() + timedelta(days=SRS_INTERVALS_DAYS[SRS_MAX_LEVEL])
    else:
        word.srs_level = 0
        word.due_at = datetime.utcnow()
    db.commit()
    db.refresh(word)
    return word


# Возвращает случайное НЕВЫУЧЕННОЕ слово пользователя.
# Если невыученных нет — возвращает None.
def get_random_unlearned_word(db: Session, owner_id: int):
    unlearned = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        models.Word.is_learned == False
    ).all()

    if not unlearned:
        return None

    # random.choice выбирает случайный элемент из списка.
    return random.choice(unlearned)


# Статистика по словам пользователя.
# Возвращает словарь — его FastAPI отдаст как JSON напрямую.
def get_words_stats(db: Session, owner_id: int, is_premium: bool = False):
    total = db.query(models.Word).filter(
        models.Word.owner_id == owner_id
    ).count()

    learned = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        models.Word.is_learned == True
    ).count()

    # Слова «к повтору» — по тому же правилу, что собирает учебную сессию.
    due = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        *due_filter()
    ).count()

    return {
        "total": total,
        "learned": learned,
        "remaining": total - learned,
        "due": due,
        # Правила, по которым клиент рисует прогресс и остатки. Отдаём их вместе
        # со статистикой, чтобы фронтенду не приходилось хранить копии
        # серверных констант: раньше SRS_MAX_LEVEL и REGEN_LIMIT были вручную
        # продублированы в dictionary.js и молча разъехались бы при изменении.
        "srs_max_level": SRS_MAX_LEVEL,
        "regen_limit": -1 if is_premium else REGEN_LIMIT,
        "words_left_today": -1 if is_premium else max(
            0, DAILY_WORD_LIMIT - count_words_created_today(db, owner_id)
        ),
    }