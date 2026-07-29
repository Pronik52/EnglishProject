"""Тесты картинок-сцен: ключ кеша, выключенный провайдер, статусы у слова."""

import pytest

from app import image_generator, models, schemas
from app.crud.words import create_word, generate_word_image, get_word
from tests.conftest import run_async


def test_scene_key_ignores_case_and_spaces():
    # Один и тот же сюжет, записанный по-разному, должен давать один файл —
    # иначе кеш не сработает и мы дважды заплатим за одну картинку.
    a = image_generator.scene_key("A boy eats an apple")
    b = image_generator.scene_key("  a  boy   eats an APPLE ")
    assert a == b


def test_seed_always_fits_signed_int32():
    """Pollinations принимает только знаковый 32-битный seed и на большие
    значения отвечает 500. Хеш из 8 hex-символов доходит до 4294967295, и
    примерно половина сцен не рисовалась бы никогда."""
    limit = 2**31 - 1
    for scene in ("a boy eats an apple", "I walk my dog in the park",
                  "a woman with an umbrella in the rain", "an old man near a lighthouse",
                  "children playing football", "a cat sleeps on the sofa"):
        seed = int(image_generator.scene_key(scene)[:7], 16)
        assert 0 <= seed <= limit, f"seed {seed} вне диапазона int32 для сцены {scene!r}"


def test_scene_key_differs_for_different_scenes():
    assert image_generator.scene_key("a boy eats an apple") != \
           image_generator.scene_key("a girl reads a book")


def test_generation_disabled_by_env(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "off")
    assert image_generator.is_enabled() is False
    assert run_async(image_generator.generate_scene_image("a boy eats an apple")) is None


def test_empty_prompt_generates_nothing(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")
    assert run_async(image_generator.generate_scene_image("")) is None
    assert run_async(image_generator.generate_scene_image("   ")) is None


def test_provider_failure_never_raises(monkeypatch):
    """Падение провайдера обязано превращаться в None, а не в исключение:
    иначе пользователь не сможет добавить слово из-за недоступной картинки."""
    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")

    async def boom(prompt):
        raise RuntimeError("провайдер недоступен")

    monkeypatch.setattr(image_generator, "_fetch_pollinations", boom)
    # Промпт делаем уникальным, чтобы не попасть в кеш с диска.
    assert run_async(image_generator.generate_scene_image("сцена которой точно нет в кеше 12345")) is None


def test_word_created_without_images_has_status_none(db_session, test_user):
    # Фикстура offline_mode выключает генерацию — слово должно создаться
    # штатно, просто без картинки.
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="apple", translation="яблоко"), test_user.id
    ))
    assert word.image_url is None
    assert word.image_status == "none"


def test_scene_prompt_is_saved_but_hidden_from_client(db_session, test_user):
    """scene_prompt нужен для будущего режима «опиши картинку», поэтому он
    сохраняется в базе, но не попадает в ответ API — иначе ответ можно списать."""
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="bridge", translation="мост"), test_user.id
    ))
    assert word.scene_prompt  # офлайн-фолбэк собирает описание из самой фразы

    payload = schemas.WordResponse.model_validate(word).model_dump()
    assert "scene_prompt" not in payload
    assert payload["image_status"] == "none"


def test_background_generation_marks_failed(db_session, test_user, monkeypatch):
    """Если провайдер не отдал картинку, слово получает статус failed —
    фронт по нему поймёт, что опрашивать больше нечего."""
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="river", translation="река"), test_user.id
    ))
    word.scene_prompt = "a river in the forest"
    word.image_status = "pending"
    db_session.commit()

    async def no_image(prompt):
        return None

    monkeypatch.setattr("app.crud.words.generate_scene_image", no_image)
    run_async(generate_word_image(word.id, test_user.id))

    db_session.expire_all()
    refreshed = get_word(db_session, word.id, test_user.id)
    assert refreshed.image_status == "failed"
    assert refreshed.image_url is None


def test_background_generation_saves_url(db_session, test_user, monkeypatch):
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="cloud", translation="облако"), test_user.id
    ))
    word.scene_prompt = "a white cloud over a field"
    word.image_status = "pending"
    db_session.commit()

    async def fake_image(prompt):
        return "/media/scenes/deadbeef.jpg"

    monkeypatch.setattr("app.crud.words.generate_scene_image", fake_image)
    run_async(generate_word_image(word.id, test_user.id))

    db_session.expire_all()
    refreshed = get_word(db_session, word.id, test_user.id)
    assert refreshed.image_status == "ready"
    assert refreshed.image_url == "/media/scenes/deadbeef.jpg"


def test_deleted_word_does_not_break_background_task(db_session, test_user, monkeypatch):
    """Пользователь может удалить слово, пока рисуется картинка.
    Фоновая задача обязана тихо завершиться, а не упасть."""
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="stone", translation="камень"), test_user.id
    ))
    word_id = word.id
    db_session.delete(word)
    db_session.commit()

    run_async(generate_word_image(word_id, test_user.id))  # не должно бросить


def test_ensure_scene_backfills_old_word(db_session, test_user, monkeypatch):
    """Слова, заведённые до появления картинок, должны получать сцену
    из своей фразы — иначе главный режим для них недоступен навсегда."""
    from app.crud.words import ensure_scene

    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")
    old = models.Word(text="dog", translation="собака",
                      phrase="I walk my dog in the park.", owner_id=test_user.id)
    db_session.add(old)
    db_session.commit()
    assert old.scene_prompt is None

    status, word = ensure_scene(db_session, old.id, test_user.id)
    assert status == "pending"
    assert word.scene_prompt          # выведена из фразы, без обращения к ИИ
    assert "dog" in word.scene_prompt
    assert word.image_status == "pending"


def test_ensure_scene_reports_disabled(db_session, test_user, monkeypatch):
    from app.crud.words import ensure_scene

    monkeypatch.setenv("IMAGE_PROVIDER", "off")
    word = models.Word(text="dog", translation="собака",
                       phrase="I walk my dog.", owner_id=test_user.id)
    db_session.add(word)
    db_session.commit()

    status, _ = ensure_scene(db_session, word.id, test_user.id)
    assert status == "disabled"


def test_ensure_scene_needs_a_phrase(db_session, test_user, monkeypatch):
    from app.crud.words import ensure_scene

    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")
    word = models.Word(text="", translation="", phrase=None, owner_id=test_user.id)
    db_session.add(word)
    db_session.commit()

    status, _ = ensure_scene(db_session, word.id, test_user.id)
    assert status == "no_phrase"


def test_scene_endpoint_prepares_old_word(client, db_session, test_user, monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")
    old = models.Word(text="dog", translation="собака",
                      phrase="I walk my dog in the park.", owner_id=test_user.id)
    db_session.add(old)
    db_session.commit()

    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post(f"/api/v1/words/{old.id}/scene", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["image_status"] == "pending"


def test_scene_endpoint_409_when_images_disabled(client, db_session, test_user, monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "off")
    old = models.Word(text="dog", translation="собака",
                      phrase="I walk my dog.", owner_id=test_user.id)
    db_session.add(old)
    db_session.commit()

    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post(f"/api/v1/words/{old.id}/scene", headers=headers)
    assert resp.status_code == 409


def test_image_endpoint_returns_status(client, test_user):
    login = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = client.post(
        "/api/v1/words",
        json={"text": "window", "translation": "окно"},
        headers=headers
    )
    assert created.status_code == 200
    word_id = created.json()["id"]

    resp = client.get(f"/api/v1/words/{word_id}/image", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"image_url": None, "image_status": "none"}


def test_image_endpoint_hides_other_users_word(client, db_session, test_user):
    from app import models

    stranger = models.User(email="stranger@example.com", hashed_password="x")
    db_session.add(stranger)
    db_session.commit()
    other_word = models.Word(text="secret", translation="секрет", owner_id=stranger.id)
    db_session.add(other_word)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/v1/words/{other_word.id}/image", headers=headers)
    assert resp.status_code == 404
