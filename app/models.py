from sqlalchemy.sql import func
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Index, Table
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


# Класс User описывает таблицу "users".
# Наследуемся от Base — так SQLAlchemy узнаёт, что это таблица.
class User(Base):
    __tablename__ = "users"  # имя таблицы в базе

    # id — первичный ключ, автоинкремент (1, 2, 3...).
    id = Column(Integer, primary_key=True, index=True)

    # email — строка, уникальная (двух одинаковых быть не может),
    # обязательная (nullable=False = не может быть пустой).
    email = Column(String, unique=True, nullable=False, index=True)

    # hashed_password — пароль храним НЕ в открытом виде, а как хеш.
    # (хеширование настроим на следующем этапе, пока просто поле)
    hashed_password = Column(String, nullable=False)

    # Уровень владения языком (CEFR): A1, A2, B1, B2, C1.
    # По нему генератор подбирает фразы нужной сложности.
    level = Column(String, nullable=False, default="A1", server_default="A1")

    # Тариф: False — бесплатный (лимит слов в день), True — Premium (безлимит).
    is_premium = Column(Boolean, nullable=False, default=False, server_default="false")

    # До какого момента действует Premium. Заложено под будущее авто-отключение
    # по таймеру (сейчас тариф снимается вручную). NULL — Premium не куплен.
    premium_until = Column(DateTime(timezone=True), nullable=True)

    # created_at — дата регистрации. server_default=func.now() значит:
    # при создании записи база сама подставит текущее время.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Обратная связь: позволяет писать user.words и получить список его слов.
    # back_populates связывает обе стороны: User.words <-> Word.owner.
    words = relationship("Word", back_populates="owner")

class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, index=True)

    # Само слово на английском и его перевод.
    text = Column(String, nullable=False)
    translation = Column(String, nullable=False)

    # Короткая фраза с этим словом — её генерирует бэкенд, чтобы слово
    # запоминалось в контексте, а не изолированно.
    phrase = Column(String, nullable=True)

    # Русский перевод фразы целиком (для показа в тренировке после ответа).
    # Заполняется при генерации фразы; для старых слов дозаполняется лениво.
    phrase_ru = Column(String, nullable=True)

    # Описание визуальной сцены к фразе (на английском) — промпт для картинки.
    # Хранится отдельно ещё и потому, что это «эталон» для будущего режима
    # «опиши картинку»: мы знаем, что на ней изображено, и можем сверить ответ
    # пользователя обычной текстовой моделью, без дорогой мультимодальной.
    scene_prompt = Column(String, nullable=True)

    # Ссылка на сгенерированную картинку вида /media/scenes/<хеш>.jpg.
    image_url = Column(String, nullable=True)

    # Состояние генерации картинки: none — не запускалась, pending — в работе,
    # ready — готова, failed — провайдер не ответил. Фронт по нему решает,
    # показывать ли заглушку и опрашивать ли слово повторно.
    image_status = Column(String, nullable=False, default="none", server_default="none")

    is_learned = Column(Boolean, default=False, nullable=False, server_default="false")

    # Сколько раз пользователь повторил слово (общий счётчик, для статистики).
    review_count = Column(Integer, default=0)

    # SRS (интервальные повторы, система Лейтнера):
    # srs_level — «коробка» 0..5, due_at — когда слово снова пора повторить.
    srs_level = Column(Integer, nullable=False, default=0, server_default="0")
    due_at = Column(DateTime, nullable=True)

    # Сколько раз для слова уже перегенерировали фразу («другая фраза»).
    # Потолок — REGEN_LIMIT на слово: каждая генерация это вызов LLM, а удачная
    # фраза находится за пару попыток. Счётчик не сбрасывается.
    regen_count = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ВНЕШНИЙ КЛЮЧ: ссылка на id пользователя из таблицы users.
    # Это поле "Владелец" в терминах 1С.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Откуда слово попало в словарь: ссылка на запись каталога либо NULL для
    # слов, добавленных вручную. Нужна, чтобы каталог мог быстро показать
    # «уже добавлено», сверяясь по идентификаторам, а не по строкам.
    catalog_word_id = Column(Integer, ForeignKey("catalog_words.id"), nullable=True, index=True)

    # СВЯЗЬ на уровне ORM: позволяет писать word.owner и получать объект User.
    # Это НЕ колонка в базе — это удобство Python-кода.
    owner = relationship("User", back_populates="words")

    __table_args__ = (
        # Один и тот же смысл нельзя завести дважды, но РАЗНЫЕ значения одного
        # слова — можно: book/книга и book/бронировать это две учебные единицы.
        # Поэтому ключ включает перевод, а не только само слово.
        # lower() — чтобы «Book» и «book» считались одним и тем же.
        Index("uq_words_owner_word_meaning", "owner_id",
              func.lower(text), func.lower(translation), unique=True),
        # Почти каждый запрос к словарю фильтрует по владельцу.
        Index("ix_words_owner_id", "owner_id"),
    )


# Связь «каталожное слово ↔ категории»: одно слово может относиться сразу к
# нескольким темам (например apple — и «Еда», и «Покупки»).
catalog_word_categories = Table(
    "catalog_word_categories",
    Base.metadata,
    Column("catalog_word_id", Integer,
           ForeignKey("catalog_words.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer,
           ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    """Тематическая категория каталога («Еда», «Путешествия» и т.д.).

    Справочник, общий для всех пользователей. slug — стабильный системный
    ключ, по которому категория ищется из кода и seed-файла; title меняется
    свободно, slug — нет.
    """
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)

    # Порядок в списке. Одинаковые значения сортируются по названию.
    sort_order = Column(Integer, nullable=False, default=100, server_default="100")

    # Скрытая категория остаётся в базе (слова на неё ссылаются), но не
    # показывается пользователю и недоступна для фильтра.
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    words = relationship("CatalogWord", secondary=catalog_word_categories,
                         back_populates="categories")


class CatalogWord(Base):
    """Запись каталога — слово, доступное ВСЕМ пользователям для выбора.

    Каталог намеренно отделён от таблицы words: там личный словарь конкретного
    человека с его прогрессом, здесь — общий справочник без владельца. Когда
    пользователь добавляет слово из каталога, создаётся отдельная запись Word
    со ссылкой catalog_word_id; сама каталожная запись остаётся общей.

    Единица каталога — ЗНАЧЕНИЕ, а не строка: book/книга и book/бронировать
    это две разные записи с разной частью речи и разными примерами.
    """
    __tablename__ = "catalog_words"

    id = Column(Integer, primary_key=True, index=True)

    text = Column(String, nullable=False)
    translation = Column(String, nullable=False)

    # Часть речи (noun/verb/adjective/adverb/phrase). В личном словаре её нет,
    # там она вычисляется на лету в phrases.py, но для каталога это осмысленные
    # кураторские данные — храним.
    part_of_speech = Column(String, nullable=True)

    # Уровень CEFR: A1..C2. Наполнение MVP — A1..B2, но модель шире.
    level = Column(String, nullable=False, index=True)

    transcription = Column(String, nullable=True)

    # Курируемый пример употребления. Он же становится учебной фразой при
    # добавлении слова в словарь — поэтому для каталожных слов не нужен
    # вызов ИИ, а качество примера выше сгенерированного.
    example_en = Column(String, nullable=True)
    example_ru = Column(String, nullable=True)

    # Чем меньше число, тем раньше слово показывается: 1 — самые частотные.
    frequency_rank = Column(Integer, nullable=False, default=1000, server_default="1000")

    # Выключенное слово не отдаётся в выдаче и не добавляется в словарь,
    # но у тех, кто уже добавил его раньше, оно продолжает работать.
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    categories = relationship("Category", secondary=catalog_word_categories,
                              back_populates="words")

    __table_args__ = (
        # Уникальность на уровне значения, а не строки слова.
        Index("uq_catalog_word_meaning",
              func.lower(text), func.lower(translation), unique=True),
        # Основной фильтр выдачи — уровень плюс активность.
        Index("ix_catalog_words_level_active", "level", "is_active"),
        # Сортировка по приоритету.
        Index("ix_catalog_words_frequency", "frequency_rank"),
    )


class ReviewLog(Base):
    """Журнал повторов: по одной записи на каждый ответ пользователя.

    Зачем нужен, если у слова уже есть review_count и srs_level: счётчики
    хранят только ИТОГ, а история ответов — то, из чего потом считается
    статистика, графики прогресса, streak и подбор интервалов под конкретного
    человека. Восстановить историю из счётчиков нельзя, поэтому пишем её сразу.

    Таблица только на добавление: записи не меняем и не удаляем.
    """
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id"), nullable=False, index=True)

    # Каким режимом отвечали: choice — выбор варианта, type — ввод слова,
    # describe — описание картинки своими словами.
    mode = Column(String, nullable=False)

    # Итог ответа и оценка 0..3 (у режимов выбора/ввода это просто 0 или 3).
    correct = Column(Boolean, nullable=False)
    grade = Column(Integer, nullable=False, default=0)

    # Что именно написал пользователь. Для режима описания это главная
    # ценность: по этим текстам видно, как человек реально владеет словом.
    answer_text = Column(String, nullable=True)

    # Уровень SRS ПОСЛЕ ответа — чтобы строить график роста, не пересчитывая
    # всю цепочку повторов заново.
    srs_level_after = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)