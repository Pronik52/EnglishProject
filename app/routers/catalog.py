"""Каталог готовых слов: уровни, категории, выдача и массовое добавление.

Все эндпоинты требуют авторизации: выдача помечает слова, которые уже есть в
словаре, а значит зависит от текущего пользователя. Идентификатор пользователя
берётся ТОЛЬКО из токена — клиент его не присылает и повлиять на него не может.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import catalog as crud_catalog
from ..auth import get_current_user

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/levels", response_model=list[schemas.LevelResponse])
def read_levels(current_user: models.User = Depends(get_current_user)):
    """Уровни, для которых наполнен каталог."""
    return crud_catalog.list_levels()


@router.get("/categories", response_model=list[schemas.CategoryResponse])
def read_categories(
    level: str = Query(None, description="Считать слова только этого уровня"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Активные категории с числом доступных слов."""
    if level:
        level = _validate_level(level)
    return crud_catalog.list_categories(db, level=level)


@router.get("/words", response_model=schemas.PaginatedCatalogResponse)
def read_catalog_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    level: str = Query(None),
    category: str = Query(None, description="slug категории"),
    search: str = Query(None),
    hide_added: bool = Query(False, description="Скрыть слова, уже добавленные в словарь"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Каталог с фильтрами и пометкой «уже в словаре».

    Уровень по умолчанию — из профиля пользователя: он уже выбирал его при
    настройке, спрашивать второй раз незачем.
    """
    level = _validate_level(level) if level else _default_level(current_user)

    result = crud_catalog.list_catalog_words(
        db, owner_id=current_user.id, level=level, category_slug=category,
        search=search, hide_added=hide_added, skip=skip, limit=limit,
    )
    pages = (result["total"] + limit - 1) // limit
    return {
        "items": result["items"],
        "total": result["total"],
        "page": skip // limit,
        "size": limit,
        "pages": pages,
    }


@router.post("/words/add", response_model=schemas.CatalogAddResult)
def add_catalog_words(
    payload: schemas.CatalogAddRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Массово добавить выбранные каталожные слова в личный словарь.

    Возвращает 200 даже при частичном успехе: разбор по добавленным,
    дублям, упёршимся в лимит и ненайденным лежит в теле ответа. Ошибкой
    считается только полностью невалидный запрос — его отсекает схема.
    """
    return crud_catalog.add_words_to_dictionary(
        db, owner_id=current_user.id, word_ids=payload.word_ids,
        is_premium=current_user.is_premium,
    )


def _validate_level(level: str) -> str:
    normalized = (level or "").strip().upper()
    if normalized not in schemas.LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"Недопустимый уровень. Возможные: {', '.join(schemas.LEVELS)}"
        )
    return normalized


def _default_level(user: models.User) -> str:
    """Уровень из профиля, если каталог для него наполнен.

    Если каталог для уровня из профиля ещё не наполнен, показываем самый
    старший наполненный: иначе выдача была бы пустой без объяснений.
    """
    level = (user.level or "A1").upper()
    return level if level in schemas.CATALOG_LEVELS else schemas.CATALOG_LEVELS[-1]
