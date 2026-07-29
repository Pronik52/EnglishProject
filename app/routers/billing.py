"""Тариф и остаток дневного лимита.

Оплата из интерфейса убрана: она была фиктивной (карта никуда не уходила), а
жёсткие лимиты вокруг неё мешали первому занятию. Модель тарифов в базе при
этом сохранена — вернётся, когда появится настоящий платёжный провайдер.

Пока её нет, ручки включения Premium закрыты флагом BILLING_DEMO_ENABLED.
Без него /activate раздавал бы Premium любому авторизованному пользователю:
кнопки в интерфейсе нет, но эндпоинт остаётся вызываемым напрямую.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import users as crud_users, words as crud_words
from ..auth import get_current_user

router = APIRouter(prefix="/billing", tags=["billing"])


def _demo_enabled() -> bool:
    return os.getenv("BILLING_DEMO_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _require_demo():
    if not _demo_enabled():
        # 404, а не 403: выключенной ручки для клиента просто не существует.
        raise HTTPException(status_code=404, detail="Not Found")


def _status(db: Session, user: models.User) -> dict:
    limit = crud_words.DAILY_WORD_LIMIT
    # Для Premium дневной лимит не действует — COUNT не нужен.
    used = 0 if user.is_premium else crud_words.count_words_created_today(db, user.id)
    return {
        "is_premium": user.is_premium,
        "premium_until": user.premium_until,
        "daily_limit": limit,
        "used_today": used,
        # Для Premium лимита нет — возвращаем -1 как признак «без ограничений».
        "remaining": -1 if user.is_premium else max(0, limit - used),
        "regen_limit": crud_words.REGEN_LIMIT,
    }


# Текущий тариф и остаток дневного лимита.
@router.get("/status", response_model=schemas.BillingStatus)
def billing_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return _status(db, current_user)


# ДЕМО-покупка Premium. Оплата фиктивная: карту не проверяем и не храним,
# сразу включаем тариф на выбранный срок (plan — 1/3/12 месяцев).
# В боевой версии сюда встанет подтверждение оплаты от провайдера
# (Stripe/YooKassa) через webhook — логика тарифа не изменится.
@router.post("/activate", response_model=schemas.BillingStatus)
def activate_premium(
    payload: schemas.PurchaseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    _require_demo()
    crud_users.set_premium(db, user=current_user, is_premium=True, months=payload.plan)
    return _status(db, current_user)


# Отмена Premium (возврат на бесплатный тариф). Временно — вручную;
# в будущем тариф будет сниматься автоматически по истечении premium_until.
# При возврате на Free обнуляем счётчики генераций фразы.
@router.post("/deactivate", response_model=schemas.BillingStatus)
def deactivate_premium(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    _require_demo()
    crud_users.set_premium(db, user=current_user, is_premium=False)
    crud_words.reset_regens(db, current_user.id)
    return _status(db, current_user)
