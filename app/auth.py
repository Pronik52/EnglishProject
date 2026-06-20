import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db
from . import models

load_dotenv()

# Читаем настройки токена из .env
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

# Тот же контекст хеширования, что и в crud.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Проверяет: совпадает ли введённый пароль с хешем из базы.
# bcrypt сам умеет сравнивать пароль с хешем (НЕ "расхешировать", а проверить).
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# Создаёт JWT-токен.
# data — что положить внутрь (мы положим email).
def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    # Считаем момент, когда токен "протухнет".
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # "exp" — стандартное поле JWT для срока годности.
    to_encode.update({"exp": expire})

    # Кодируем и подписываем токен секретным ключом.
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Проверяет токен и достаёт из него email. Если токен битый/просрочен — вернёт None.
def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")  # "sub" (subject) — кого касается токен
        return email
    except JWTError:
        return None
    

# Говорим FastAPI, что токен берётся со эндпоинта /login.
# tokenUrl="login" — для документации и кнопки Authorize в /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ГЛАВНАЯ функция этапа.
# FastAPI сам достанет токен из заголовка Authorization и передаст в token.
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Заготовка ошибки 401 — будем её бросать при любой проблеме с токеном.
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Проверяем токен и достаём email (функция из этапа 4).
    email = decode_access_token(token)
    if email is None:
        raise credentials_exception  # токен битый или просрочен

    # 2. Ищем пользователя в базе по email из токена.
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception  # юзера удалили, а токен ещё на руках

    # 3. Всё ок — возвращаем объект пользователя.
    return user