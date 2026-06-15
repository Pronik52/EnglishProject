# Импортируем engine (соединение) и Base (реестр всех моделей).
from database import engine, Base

# ВАЖНО: импортируем models, чтобы класс User зарегистрировался в Base.
# Без этой строки Base "не узнает" о таблице users.
import models

# Команда: создать в базе все таблицы, которые зарегистрированы в Base.
# Если таблица уже есть — SQLAlchemy её НЕ пересоздаёт (не сотрёт данные).
Base.metadata.create_all(bind=engine)

print("Таблицы успешно созданы!")