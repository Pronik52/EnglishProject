from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..phrases import generate_phrase, generate_variants, get_phrase
from ..ai_generator import ai_generate_phrase
from ..translator import translate_to_ru

# Сколько слов в сутки можно добавить на бесплатном тарифе. Premium — без лимита.
FREE_DAILY_WORD_LIMIT = 10

# Сколько раз можно перегенерировать фразу для ОДНОГО слова на бесплатном тарифе.
# Дальше кнопка «другая фраза» становится Premium-функцией. Premium — без лимита.
FREE_REGEN_LIMIT = 5

# --- SRS (интервальные повторы, система Лейтнера) ---
SRS_MAX_LEVEL = 5
# Дней до следующего повтора после достижения уровня (индекс = уровень).
# Уровень 0 (новое слово или ошибка) — повтор сразу.
SRS_INTERVALS_DAYS = [0, 1, 3, 7, 14, 30]


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
    db_word = models.Word(
        text=word.text,
        translation=word.translation,
        phrase=data["phrase_en"],
        phrase_ru=data["phrase_ru"],
        srs_level=0,
        due_at=datetime.utcnow(),  # новое слово сразу «к повтору»
        owner_id=owner_id
    )
    db.add(db_word)
    db.commit()
    db.refresh(db_word)
    return db_word


# Свежая случайная фраза для слова + её русский перевод. Сначала ИИ (даёт разный
# результат каждый раз), при недоступности — оффлайн-варианты. Не повторяем текущую.
async def _fresh_phrase(word: str, translation: str, level: str, avoid: str):
    ai = await ai_generate_phrase(word, translation, level, avoid=avoid)
    if ai and ai["phrase_en"] and ai["phrase_en"] != avoid:
        en = ai["phrase_en"]
        return en, (ai["phrase_ru"] or translate_to_ru(en))
    # Фолбэк: детерминированные варианты, берём отличный от текущего.
    variants = generate_variants(word, translation, level=level, count=3)
    en = next((v for v in variants if v != avoid), variants[0])
    return en, translate_to_ru(en)


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

    if not is_premium and (word.regen_count or 0) >= FREE_REGEN_LIMIT:
        return "limit", word

    word.phrase, word.phrase_ru = await _fresh_phrase(word.text, word.translation, level, avoid=word.phrase)
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
    db.commit()
    db.refresh(word)
    return word


# Ответ в режиме викторины: верно → повышаем SRS-уровень и интервал,
# неверно → сброс на 0 и повтор сразу.
def answer_word(db: Session, word_id: int, owner_id: int, correct: bool):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    _apply_srs(word, correct=correct)
    db.commit()
    db.refresh(word)
    return word


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
def get_words_stats(db: Session, owner_id: int):
    total = db.query(models.Word).filter(
        models.Word.owner_id == owner_id
    ).count()

    learned = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        models.Word.is_learned == True
    ).count()

    # Слова «к повтору»: невыученные, у которых срок повтора наступил (или не задан).
    now = datetime.utcnow()
    due = db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        models.Word.is_learned == False,
        (models.Word.due_at == None) | (models.Word.due_at <= now)
    ).count()

    return {
        "total": total,
        "learned": learned,
        "remaining": total - learned,
        "due": due
    }