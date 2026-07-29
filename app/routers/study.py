"""Учебная сессия: что повторять сейчас и каким режимом.

Отдельный роутер, а не ещё один эндпоинт в words: сессия — это не выборка из
словаря, а самостоятельное понятие со своими правилами отбора и своей
лестницей режимов. Ответы на карточки по-прежнему уходят в уже существующие
PATCH /words/{id}/answer и POST /words/{id}/describe — дублировать их здесь
не нужно.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import study as crud_study
from ..auth import get_current_user

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/session", response_model=schemas.StudySession)
def read_session(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    size: int = Query(crud_study.SESSION_DEFAULT_SIZE, ge=1,
                      le=crud_study.SESSION_MAX_SIZE),
    ahead: bool = Query(False, description="Заниматься сверх плана: игнорировать срок повтора"),
):
    """Карточки на сейчас с уже назначенными режимами и вариантами ответа.

    Пустой cards при ahead=false — не ошибка, а «на сегодня всё»: клиент
    показывает соответствующий экран и предлагает заниматься сверх плана.
    """
    return crud_study.build_session(
        db, owner_id=current_user.id, size=size, ahead=ahead,
        level=current_user.level,
    )
