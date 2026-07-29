import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import models

client = TestClient(app)

def test_api_flow(db_session, test_user):
    """Тестирование полного потока работы с API"""

    # 1. Получаем токен
    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Создаем слово
    create_response = client.post(
        "/api/v1/words",
        json={"text": "integration", "translation": "интеграция"},
        headers=headers
    )
    assert create_response.status_code == 200
    word_data = create_response.json()
    word_id = word_data["id"]

    # 3. Получаем список слов
    list_response = client.get("/api/v1/words", headers=headers)
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert len(list_data["items"]) == 1
    assert list_data["total"] == 1
    assert list_data["page"] == 0
    assert list_data["size"] == 100

    # 4. Получаем конкретное слово
    get_response = client.get(f"/api/v1/words/{word_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["text"] == "integration"

    # 5. Повторяем слово несколько раз
    for i in range(4):  # LEARNED_THRESHOLD = 5
        review_response = client.patch(f"/api/v1/words/{word_id}/review", headers=headers)
        assert review_response.status_code == 200
        assert review_response.json()["review_count"] == i + 1

    # 6. Проверяем что слово помечено как выученное
    final_review_response = client.patch(f"/api/v1/words/{word_id}/review", headers=headers)
    assert final_review_response.status_code == 200
    assert final_review_response.json()["is_learned"] == True
    assert final_review_response.json()["review_count"] == 5

    # 7. Получаем статистику
    stats_response = client.get("/api/v1/words/stats", headers=headers)
    assert stats_response.status_code == 200
    stats_data = stats_response.json()
    assert stats_data["total"] == 1
    assert stats_data["learned"] == 1
    assert stats_data["remaining"] == 0

    # 8. Удаляем слово
    delete_response = client.delete(f"/api/v1/words/{word_id}", headers=headers)
    assert delete_response.status_code == 200

    # 9. Проверяем что слово удалено
    get_deleted_response = client.get(f"/api/v1/words/{word_id}", headers=headers)
    assert get_deleted_response.status_code == 404

def test_pagination(db_session, test_user):
    """Тестирование пагинации"""

    # Создаем несколько слов
    login = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for i in range(7):
        client.post(
            "/api/v1/words",
            json={"text": f"word{i}", "translation": f"слово{i}"},
            headers=headers
        )

    # Тестируем первую страницу
    response1 = client.get("/api/v1/words?skip=0&limit=3", headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["items"]) == 3
    assert data1["total"] == 7
    assert data1["page"] == 0
    assert data1["size"] == 3
    assert data1["pages"] == 3

    # Тестируем вторую страницу
    response2 = client.get("/api/v1/words?skip=3&limit=3", headers=headers)
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["items"]) == 3
    assert data2["page"] == 1

    # Тестируем третью страницу
    response3 = client.get("/api/v1/words?skip=6&limit=3", headers=headers)
    assert response3.status_code == 200
    data3 = response3.json()
    assert len(data3["items"]) == 1
    assert data3["page"] == 2

def test_search_and_filter(db_session, test_user):
    """Тестирование поиска и фильтрации"""

    login = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Создаем слова для тестирования
    client.post("/api/v1/words", json={"text": "apple", "translation": "яблоко"}, headers=headers)
    client.post("/api/v1/words", json={"text": "banana", "translation": "банан"}, headers=headers)
    client.post("/api/v1/words", json={"text": "learned", "translation": "выученное", "is_learned": True}, headers=headers)

    # Тестируем поиск
    search_response = client.get("/api/v1/words?search=app", headers=headers)
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert len(search_data["items"]) == 1
    assert search_data["items"][0]["text"] == "apple"

    # Тестируем фильтр по выученным словам
    filter_response = client.get("/api/v1/words?is_learned=true", headers=headers)
    assert filter_response.status_code == 200
    filter_data = filter_response.json()
    assert len(filter_data["items"]) == 1
    assert filter_data["items"][0]["text"] == "learned"

def test_newcomer_path_from_registration_to_first_answer(db_session):
    """Путь новичка целиком: регистрация → набор из каталога → первая карточка.

    Это тот самый сценарий, ради которого делался мастер первого запуска.
    Проверяем главное: первая карточка человека, который только что
    зарегистрировался, НЕ требует писать текст на английском.
    """
    # 1. Каталог, из которого мастер берёт стартовый набор.
    topic = models.Category(slug="basics", title="Основное")
    db_session.add(topic)
    db_session.add_all([
        models.CatalogWord(text=t, translation=r, level="A1",
                           frequency_rank=i, categories=[topic])
        for i, (t, r) in enumerate([
            ("apple", "яблоко"), ("bread", "хлеб"), ("water", "вода"),
            ("house", "дом"), ("river", "река"), ("light", "свет"),
        ])
    ])
    db_session.commit()

    # 2. Регистрация и вход.
    email = "newcomer@example.com"
    assert client.post("/api/v1/auth/register",
                       json={"email": email, "password": "Secret123"}).status_code == 200
    login = client.post("/api/v1/auth/token",
                        data={"username": email, "password": "Secret123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 3. Словарь пуст — фронтенд по этому признаку показывает мастер.
    assert client.get("/api/v1/words/stats", headers=headers).json()["total"] == 0

    # 4. Шаги мастера: уровень, тема, готовый набор.
    assert client.patch("/api/v1/auth/level", json={"level": "A1"},
                        headers=headers).status_code == 200
    categories = client.get("/api/v1/catalog/categories?level=A1", headers=headers).json()
    assert [c["slug"] for c in categories] == ["basics"]

    starter = client.get("/api/v1/catalog/words?level=A1&category=basics&limit=10",
                         headers=headers).json()
    added = client.post("/api/v1/catalog/words/add",
                        json={"word_ids": [w["id"] for w in starter["items"]]},
                        headers=headers).json()
    assert added["added_count"] == 6

    # 5. Первая сессия: все слова новые, значит все карточки — на узнавание.
    session = client.get("/api/v1/study/session", headers=headers).json()
    assert session["due_total"] == 6
    assert len(session["cards"]) == 6
    assert {c["mode"] for c in session["cards"]} == {"choice"}
    first = session["cards"][0]
    assert len(first["options"]) == 4
    assert first["word"]["text"] in first["options"]

    # 6. Ответ уводит слово из сегодняшней сессии.
    word_id = first["word"]["id"]
    answered = client.patch(f"/api/v1/words/{word_id}/answer",
                            json={"correct": True}, headers=headers)
    assert answered.status_code == 200
    assert answered.json()["srs_level"] == 1

    second = client.get("/api/v1/study/session", headers=headers).json()
    assert second["due_total"] == 5
    assert word_id not in [c["word"]["id"] for c in second["cards"]]


def test_session_grows_harder_as_word_is_learned(db_session, test_user):
    """Лестница сложности: одно и то же слово меняет режим по мере повторов."""
    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Отвлекатели, чтобы режим выбора вообще был возможен.
    for i in range(5):
        client.post("/api/v1/words", json={"text": f"filler{i}", "translation": f"с{i}"},
                    headers=headers)
    target = client.post("/api/v1/words",
                         json={"text": "lighthouse", "translation": "маяк"},
                         headers=headers).json()

    def mode_of(word_id):
        session = client.get("/api/v1/study/session?ahead=true&size=50",
                             headers=headers).json()
        card = next(c for c in session["cards"] if c["word"]["id"] == word_id)
        return card["mode"]

    assert mode_of(target["id"]) == "choice"          # srs_level 0

    client.patch(f"/api/v1/words/{target['id']}/answer",
                 json={"correct": True}, headers=headers)
    client.patch(f"/api/v1/words/{target['id']}/answer",
                 json={"correct": True}, headers=headers)
    # srs_level 2 — узнавание пройдено, теперь надо вспомнить и вписать.
    assert mode_of(target["id"]) == "type"


def test_error_handling(db_session, test_user):
    """Тестирование обработки ошибок"""

    login = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Тестируем доступ к несуществующему слову
    response = client.get("/api/v1/words/999", headers=headers)
    assert response.status_code == 404
    data = response.json()
    assert "Слово не найдено" in data["error"]["message"]

    # Тестируем невалидные данные
    invalid_response = client.post(
        "/api/v1/words",
        json={"text": "", "translation": ""},
        headers=headers
    )
    assert invalid_response.status_code == 422
    invalid_data = invalid_response.json()
    assert "validation_error" in invalid_data["error"]["code"]
    assert "Поле не может быть пустым" in str(invalid_data["error"]["details"])
