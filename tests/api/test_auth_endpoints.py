"""Pruebas de la capa HTTP con TestClient. Los adaptadores reales (SQLAlchemy,
bcrypt, jose) se reemplazan por los fakes de conftest.py via
app.dependency_overrides -- nunca se toca una base de datos real aqui.
"""

import pytest
from fastapi.testclient import TestClient

from interfaces.api.deps import (
    get_id_generator,
    get_password_hasher,
    get_token_service,
    get_user_repository,
)
from interfaces.api.main import create_app


@pytest.fixture
def client(user_repository, password_hasher, token_service, id_generator) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_password_hasher] = lambda: password_hasher
    app.dependency_overrides[get_token_service] = lambda: token_service
    app.dependency_overrides[get_id_generator] = lambda: id_generator
    return TestClient(app)


def test_registro_devuelve_201_y_no_expone_el_password(client: TestClient):
    response = client.post(
        "/auth/registro",
        json={"name": "Ana", "email": "ana@example.com", "password": "secret123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert "password" not in body
    assert "password_hash" not in body


def test_registro_duplicado_devuelve_409(client: TestClient):
    payload = {"name": "Ana", "email": "ana@example.com", "password": "secret123"}
    client.post("/auth/registro", json=payload)

    response = client.post("/auth/registro", json=payload)

    assert response.status_code == 409


def test_login_correcto_devuelve_token(client: TestClient):
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": "ana@example.com", "password": "secret123"},
    )

    response = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "secret123"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_incorrecto_devuelve_401(client: TestClient):
    response = client.post(
        "/auth/login", json={"email": "nadie@example.com", "password": "lo-que-sea"}
    )

    assert response.status_code == 401


def test_me_sin_token_devuelve_401(client: TestClient):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_con_token_devuelve_el_usuario(client: TestClient):
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": "ana@example.com", "password": "secret123"},
    )
    login = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "secret123"}
    )
    token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "ana@example.com"


def test_health_liveness_no_depende_de_nada():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
