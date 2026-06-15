from fastapi import FastAPI

from .routers import auth as auth_router
from .routers import words as words_router

app = FastAPI(title="English Learning API")


# Подключаем роутеры. include_router добавляет все их эндпоинты в приложение.
app.include_router(auth_router.router)
app.include_router(words_router.router)


@app.get("/")
def root():
    return {"message": "English Learning API работает"}