from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import words as crud_words
from ..auth import get_current_user
from ..phrases import generate_variants

router = APIRouter(prefix="/words", tags=["words"])


# Предпросмотр фраз для слова, которое пользователь ещё не сохранил.
# Статический маршрут — держим ДО /{word_id}.
@router.post("/preview-phrase", response_model=schemas.PhrasePreviewResponse)
def preview_phrase(
    payload: schemas.PhrasePreviewRequest,
    current_user: models.User = Depends(get_current_user)
):
    return {
        "text": payload.text,
        "phrases": generate_variants(payload.text, payload.translation, level=current_user.level, count=3)
    }


@router.post("", response_model=schemas.WordResponse)
def create_word(
    word: schemas.WordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return crud_words.create_word(db, word=word, owner_id=current_user.id, level=current_user.level)


@router.get("", response_model=schemas.PaginatedWordResponse)
def read_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    is_learned: bool = Query(None)
):
    result = crud_words.get_words_by_owner(
        db,
        owner_id=current_user.id,
        skip=skip,
        limit=limit,
        search=search,
        is_learned=is_learned
    )

    # Рассчитываем количество страниц
    pages = (result["total"] + limit - 1) // limit

    return {
        "items": result["items"],
        "total": result["total"],
        "page": skip // limit,
        "size": limit,
        "pages": pages
    }

# Получить случайное невыученное слово.
# ВАЖНО: этот маршрут должен быть ДО /{word_id} !
@router.get("/random", response_model=schemas.WordResponse)
def get_random_word(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.get_random_unlearned_word(db, owner_id=current_user.id)
    if word is None:
        raise HTTPException(
            status_code=404,
            detail="Невыученных слов нет — всё выучено или словарь пуст!"
        )
    return word


# Статистика пользователя.
# Тоже ДО /{word_id} — по той же причине.
@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return crud_words.get_words_stats(db, owner_id=current_user.id)


# Повторить слово: review_count + 1, автоматический is_learned при >= 5.
@router.patch("/{word_id}/review", response_model=schemas.WordResponse)
def review_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.review_word(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


# Сгенерировать другую фразу для уже сохранённого слова.
@router.patch("/{word_id}/regenerate-phrase", response_model=schemas.WordResponse)
def regenerate_phrase(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.regenerate_phrase(db, word_id=word_id, owner_id=current_user.id, level=current_user.level)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


# Ответ в викторине: +1 при верном выборе слова, −1 при ошибке.
@router.patch("/{word_id}/answer", response_model=schemas.WordResponse)
def answer_word(
    word_id: int,
    payload: schemas.AnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.answer_word(
        db, word_id=word_id, owner_id=current_user.id, correct=payload.correct
    )
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


# Сбросить прогресс повторений по слову (счётчик → 0, снять "выучено").
@router.patch("/{word_id}/reset", response_model=schemas.WordResponse)
def reset_word_reviews(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.reset_reviews(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


# Вручную отметить слово как выученное или нет.
@router.patch("/{word_id}/learned", response_model=schemas.WordResponse)
def update_learned(
    word_id: int,
    payload: schemas.WordLearnedUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.toggle_learned(
        db,
        word_id=word_id,
        owner_id=current_user.id,
        is_learned=payload.is_learned
    )
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word

@router.get("/{word_id}", response_model=schemas.WordResponse)
def read_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.get_word(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


@router.delete("/{word_id}")
def remove_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ok = crud_words.delete_word(db, word_id=word_id, owner_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return {"detail": "Слово удалено"}