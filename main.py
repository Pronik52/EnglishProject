from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import crud
from database import SessionLocal

app = FastAPI()


# Зависимость: создаёт сессию БД на время одного запроса и закрывает после.
# yield отдаёт сессию в обработчик, а после ответа — закрывает её (finally).
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"message": "Привет! Сервер работает."}


# POST-эндпоинт регистрации.
# response_model=schemas.UserResponse — гарантирует, что в ответ уйдёт
# только email/id/created_at (без пароля), даже если вернём объект User.
@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Проверяем, не занят ли email.
    existing = crud.get_user_by_email(db, email=user.email)
    if existing:
        # Если есть — возвращаем ошибку 400 (некорректный запрос).
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    # 2. Создаём пользователя и возвращаем его.
    return crud.create_user(db, user=user)