import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import models

client = TestClient(app)

def test_api_flow(db_session, test_user):
    """Тестирование полного потока работы с API"""

    # 1. Получаем токен
    login_response = client.post(
        "/api/v1/auth/login",
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
        "/api/v1/auth/login",
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
        "/api/v1/auth/login",
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

def test_error_handling(db_session, test_user):
    """Тестирование обработки ошибок"""

    login = client.post(
        "/api/v1/auth/login",
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