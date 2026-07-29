import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas, models
from ..crud import users as crud_users
from .. import auth

# Все эндпоинты этого роутера попадут в группу "auth" в /docs.
router = APIRouter(tags=["auth"])

ACCESS_TOKEN_MAX_AGE = (
    auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60
)

COOKIE_PATH = "/"
# Прежние сессии выдавались с path="/api/v1". Такая cookie не перезаписывается
# новой и продолжает уезжать на сервер параллельно с ней, поэтому logout обязан
# гасить оба варианта — иначе у старого пользователя останется мёртвый csrf_token.
LEGACY_COOKIE_PATH = "/api/v1"


def _cookie_secure() -> bool:
    """В production в .env обязательно COOKIE_SECURE=true; localhost работает по HTTP."""
    return os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _set_session_cookies(response: Response, access_token: str, csrf_token: str) -> None:
    cookie_options = {
        "max_age": ACCESS_TOKEN_MAX_AGE,
        "secure": _cookie_secure(),
        "samesite": "lax",
        # path обязан быть "/", а не "/api/v1": браузер отдаёт в document.cookie
        # только cookie, чей path совпадает с адресом страницы. SPA живёт на /app,
        # и при path="/api/v1" фронтенд не видел csrf_token — заголовок
        # X-CSRF-Token не отправлялся, и любой POST падал с 403.
        "path": COOKIE_PATH,
    }
    response.set_cookie(
        key=auth.ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        **cookie_options,
    )
    # Этот token намеренно доступен JavaScript: фронтенд отправляет его в
    # X-CSRF-Token, а сервер сверяет с подписанным claim внутри access JWT.
    response.set_cookie(
        key=auth.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        **cookie_options,
    )


def _authenticate_or_401(form_data: OAuth2PasswordRequestForm, db: Session):
    user = crud_users.authenticate_user(
        db,
        email=form_data.username,
        password=form_data.password,
    )
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    return user

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud_users.get_user_by_email(db, email=user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    return crud_users.create_user(db, user=user)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Browser login: JWT остаётся недоступным JavaScript в HttpOnly cookie."""
    user = _authenticate_or_401(form_data, db)
    csrf_token = secrets.token_urlsafe(32)
    access_token = auth.create_access_token(
        data={"sub": user.email, "csrf": csrf_token}
    )
    _set_session_cookies(response, access_token, csrf_token)


@router.post("/token", response_model=schemas.Token)
def create_bearer_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 endpoint для Swagger и внешних API-клиентов, не для SPA."""
    user = _authenticate_or_401(form_data, db)
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    """Удаляет обе cookie; JavaScript не может удалить HttpOnly access cookie сам."""
    for path in (COOKIE_PATH, LEGACY_COOKIE_PATH):
        cookie_options = {
            "path": path,
            "secure": _cookie_secure(),
            "samesite": "lax",
        }
        response.delete_cookie(key=auth.ACCESS_COOKIE_NAME, httponly=True, **cookie_options)
        response.delete_cookie(key=auth.CSRF_COOKIE_NAME, httponly=False, **cookie_options)


@router.get("/me", response_model=schemas.UserResponse)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.patch("/level", response_model=schemas.UserResponse)
def update_level(
    payload: schemas.LevelUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud_users.update_level(db, user=current_user, level=payload.level)
