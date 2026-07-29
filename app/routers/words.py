from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
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
async def create_word(
    word: schemas.WordCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Защита от злоупотреблений: не больше DAILY_WORD_LIMIT новых слов в сутки.
    if not current_user.is_premium:
        used = crud_words.count_words_created_today(db, current_user.id)
        if used >= crud_words.DAILY_WORD_LIMIT:
            raise HTTPException(
                status_code=402,
                detail=(f"На сегодня добавлено максимум слов "
                        f"({crud_words.DAILY_WORD_LIMIT}). Продолжим завтра — "
                        f"а пока лучше повторить то, что уже есть.")
            )
    try:
        created = await crud_words.create_word(
            db, word=word, owner_id=current_user.id, level=current_user.level
        )
    except crud_words.DuplicateWordError:
        raise HTTPException(
            status_code=409,
            detail=f"«{word.text}» с таким переводом уже есть в вашем словаре."
        )
    _schedule_image(background_tasks, created, current_user.id)
    return created


# Ставит дорисовку картинки в фон, если она этому слову нужна. Ответ уходит
# пользователю сразу, картинка подтягивается позже опросом /{word_id}/image.
def _schedule_image(background_tasks: BackgroundTasks, word: models.Word, owner_id: int):
    if word is not None and word.image_status == "pending":
        background_tasks.add_task(crud_words.generate_word_image, word.id, owner_id)


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
    return crud_words.get_words_stats(
        db, owner_id=current_user.id, is_premium=current_user.is_premium
    )


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
async def regenerate_phrase(
    word_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    status, word = await crud_words.regenerate_phrase(
        db, word_id=word_id, owner_id=current_user.id,
        level=current_user.level, is_premium=current_user.is_premium
    )
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Слово не найдено")
    if status == "limit":
        raise HTTPException(
            status_code=402,
            detail=(f"Для этого слова фраза уже менялась "
                    f"{crud_words.REGEN_LIMIT} раз — этого обычно более чем "
                    f"достаточно, чтобы подобрать удачную.")
        )
    # Фраза сменилась — к новой сцене нужна новая картинка.
    _schedule_image(background_tasks, word, current_user.id)
    return word


# Подготовить сцену для слова, у которого её ещё нет (слова, заведённые до
# появления картинок). Фронт дёргает этот адрес, когда открывает такое слово
# в режиме описания, — тогда картинка догенерируется прямо в сессии.
@router.post("/{word_id}/scene")
def prepare_scene(
    word_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    status, word = crud_words.ensure_scene(db, word_id=word_id, owner_id=current_user.id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Слово не найдено")
    if status == "disabled":
        raise HTTPException(
            status_code=409,
            detail="Генерация картинок выключена в настройках сервера."
        )
    if status == "no_phrase":
        raise HTTPException(
            status_code=409,
            detail="У слова нет фразы, из которой можно построить картинку."
        )
    _schedule_image(background_tasks, word, current_user.id)
    return {"image_url": word.image_url, "image_status": word.image_status}


# Состояние картинки к слову. Фронт опрашивает этот адрес, пока статус
# "pending": ответ лёгкий, в отличие от полного объекта слова.
@router.get("/{word_id}/image")
def word_image(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud_words.get_word(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return {"image_url": word.image_url, "image_status": word.image_status}


# Русский перевод фразы целиком (для показа в тренировке после ответа).
# Лениво переводит и кеширует, если перевод ещё не сохранён.
@router.get("/{word_id}/phrase-translation")
def phrase_translation(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ru = crud_words.get_phrase_translation(db, word_id=word_id, owner_id=current_user.id)
    if ru is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return {"phrase_ru": ru}


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


# Главный режим: пользователь описал картинку своими словами, ИИ разбирает ответ.
@router.post("/{word_id}/describe", response_model=schemas.DescribeResponse)
async def describe_word(
    word_id: int,
    payload: schemas.DescribeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    status, word, verdict = await crud_words.describe_word(
        db, word_id=word_id, owner_id=current_user.id, answer=payload.text,
        level=current_user.level, is_premium=current_user.is_premium
    )
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Слово не найдено")
    if status == "no_scene":
        raise HTTPException(
            status_code=409,
            detail="К этому слову ещё нет картинки — опишите её, когда она появится."
        )
    if status == "limit":
        raise HTTPException(
            status_code=402,
            detail=(f"На сегодня проверок описания больше нет "
                    f"({crud_words.DAILY_DESCRIBE_LIMIT} в день). "
                    f"Режимы выбора и ввода работают без ограничений.")
        )

    left = -1 if current_user.is_premium else max(
        0, crud_words.DAILY_DESCRIBE_LIMIT
        - crud_words.count_describes_today(db, current_user.id)
    )
    return {
        "verdict": {**verdict, "correct": verdict["grade"] >= crud_words.PASS_GRADE},
        "word": word,
        "describes_left": left,
    }


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