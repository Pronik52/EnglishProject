from sqlalchemy.orm import Session

from .. import models, schemas

# Создаёт слово для конкретного владельца.
# owner_id передаём отдельно — он берётся из токена, а не из схемы.
def create_word(db: Session, word: schemas.WordCreate, owner_id: int):
    db_word = models.Word(
        text=word.text,
        translation=word.translation,
        owner_id=owner_id
    )
    db.add(db_word)
    db.commit()
    db.refresh(db_word)
    return db_word


# Возвращает ВСЕ слова конкретного пользователя.
def get_words_by_owner(db: Session, owner_id: int):
    return db.query(models.Word).filter(models.Word.owner_id == owner_id).all()


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