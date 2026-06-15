from app.database import Base, engine
from app import models  # важно: импортировать, чтобы модели зарегистрировались

Base.metadata.create_all(bind=engine)
print("Таблицы созданы")