from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import users as crud_users, words as crud_words
from ..auth import get_current_user

router = APIRouter(prefix="/billing", tags=["billing"])


def _status(db: Session, user: models.User) -> dict:
    limit = crud_words.FREE_DAILY_WORD_LIMIT
    # Для Premium дневной лимит не действует — COUNT не нужен.
    used = 0 if user.is_premium else crud_words.count_words_created_today(db, user.id)
    return {
        "is_premium": user.is_premium,
        "daily_limit": limit,
        "used_today": used,
        # Для Premium лимита нет — возвращаем -1 как признак «без ограничений».
        "remaining": -1 if user.is_premium else max(0, limit - used),
    }


# Текущий тариф и остаток дневного лимита.
@router.get("/status", response_model=schemas.BillingStatus)
def billing_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return _status(db, current_user)


# ДЕМО-активация Premium. В боевой версии сюда встанет подтверждение оплаты
# от провайдера (Stripe/YooKassa) через webhook — логика тарифа не изменится.
@router.post("/activate", response_model=schemas.BillingStatus)
def activate_premium(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    crud_users.set_premium(db, user=current_user, is_premium=True)
    return _status(db, current_user)


# Отмена Premium (возврат на бесплатный тариф).
@router.post("/deactivate", response_model=schemas.BillingStatus)
def deactivate_premium(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    crud_users.set_premium(db, user=current_user, is_premium=False)
    return _status(db, current_user)
