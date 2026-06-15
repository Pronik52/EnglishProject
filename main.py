from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import crud
from database import SessionLocal
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from auth import get_current_user
import auth

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

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm даёт нам поля username и password из формы.
    # ВАЖНО: поле называется "username", но мы кладём туда email.
    user = crud.authenticate_user(db, email=form_data.username, password=form_data.password)

    if not user:
        # Одна общая ошибка и для "нет юзера", и для "неверный пароль".
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    # Создаём токен, кладём в "sub" email пользователя.
    access_token = auth.create_access_token(data={"sub": user.email})

    # Возвращаем токен в стандартном формате OAuth2.
    return {"access_token": access_token, "token_type": "bearer"}

# Защищённый эндпоинт: вернёт данные ТЕКУЩЕГО пользователя.
# Depends(get_current_user) = "сюда пускать только с валидным токеном".
# Если токена нет/он плохой — FastAPI вернёт 401 ещё до тела функции.
@app.get("/me", response_model=schemas.UserResponse)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    # current_user — это объект User, который вернул get_current_user.
    # response_model=UserResponse гарантирует, что пароль не утечёт в ответ.
    return current_user

# Создать слово. Защищён токеном. Владелец = текущий пользователь.
@app.post("/words", response_model=schemas.WordResponse)
def create_word(
    word: schemas.WordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # owner_id берём из токена (current_user.id), а НЕ из тела запроса.
    return crud.create_word(db, word=word, owner_id=current_user.id)

# Получить список СВОИХ слов.
@app.get("/words", response_model=list[schemas.WordResponse])
def read_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return crud.get_words_by_owner(db, owner_id=current_user.id)


# Получить одно своё слово по id.
@app.get("/words/{word_id}", response_model=schemas.WordResponse)
def read_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    word = crud.get_word(db, word_id=word_id, owner_id=current_user.id)
    if word is None:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return word


# Удалить своё слово по id.
@app.delete("/words/{word_id}")
def remove_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ok = crud.delete_word(db, word_id=word_id, owner_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Слово не найдено")
    return {"detail": "Слово удалено"}