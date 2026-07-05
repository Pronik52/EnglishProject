from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..phrases import generate_phrase, generate_variants

# Создаёт слово для конкретного владельца.
# owner_id передаём отдельно — он берётся из токена, а не из схемы.
# Бэкенд сразу генерирует короткую фразу с этим словом для запоминания.
def create_word(db: Session, word: schemas.WordCreate, owner_id: int, level: str = "A1"):
    db_word = models.Word(
        text=word.text,
        translation=word.translation,
        phrase=generate_phrase(word.text, word.translation, level=level),
        owner_id=owner_id
    )
    db.add(db_word)
    db.commit()
    db.refresh(db_word)
    return db_word


# Генерирует новую фразу для существующего слова (кнопка "другая фраза").
def regenerate_phrase(db: Session, word_id: int, owner_id: int, level: str = "A1"):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    # Выбираем вариант, отличающийся от текущего, если это возможно.
    variants = generate_variants(word.text, word.translation, level=level, count=3)
    new_phrase = next((v for v in variants if v != word.phrase), variants[0])

    word.phrase = new_phrase
    db.commit()
    db.refresh(word)
    return word


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

# Увеличивает счётчик повторений на 1.
# Если достигли порога LEARNED_THRESHOLD — автоматически помечает как выученное.
LEARNED_THRESHOLD = 5  # сколько повторений нужно для автоматического is_learned

def review_word(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    word.review_count += 1

    # Автоматически помечаем выученным, если повторений достаточно.
    if word.review_count >= LEARNED_THRESHOLD:
        word.is_learned = True

    db.commit()
    db.refresh(word)
    return word


# Ответ в режиме викторины: correct=True → +1 повторение (как review),
# correct=False → −1 (не ниже нуля). Счётчик управляет автоотметкой "выучено".
def answer_word(db: Session, word_id: int, owner_id: int, correct: bool):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    if correct:
        word.review_count += 1
    else:
        word.review_count = max(0, word.review_count - 1)

    # Синхронизируем "выучено" со счётчиком повторений.
    word.is_learned = word.review_count >= LEARNED_THRESHOLD

    db.commit()
    db.refresh(word)
    return word


# Сбрасывает прогресс по слову: обнуляет счётчик повторений и снимает
# отметку "выучено", чтобы учить слово заново с нуля.
def reset_reviews(db: Session, word_id: int, owner_id: int):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    word.review_count = 0
    word.is_learned = False
    db.commit()
    db.refresh(word)
    return word


# Вручную переключает is_learned (True → False или False → True).
def toggle_learned(db: Session, word_id: int, owner_id: int, is_learned: bool):
    word = get_word(db, word_id=word_id, owner_id=owner_id)
    if word is None:
        return None

    word.is_learned = is_learned
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

    return {
        "total": total,
        "learned": learned,
        "remaining": total - learned
    }