import os
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext
from dotenv import load_dotenv

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