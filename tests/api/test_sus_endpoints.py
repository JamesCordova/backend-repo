from fastapi.testclient import TestClient


def login(client: TestClient, email: str = "ana@example.com") -> str:
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": email, "password": "secret123"},
    )
    response = client.post("/auth/login", json={"email": email, "password": "secret123"})
    return response.json()["access_token"]


def _neutral_responses() -> list[dict]:
    return [{"question_number": i, "score": 3} for i in range(1, 11)]


def test_enviar_cuestionario_sin_token_devuelve_401(client: TestClient):
    response = client.post("/cuestionarios-sus", json={"responses": _neutral_responses()})

    assert response.status_code == 401


def test_flujo_completo_enviar_y_consultar(client: TestClient):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/cuestionarios-sus", json={"responses": _neutral_responses()}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["score"] == 50.0
    assert len(body["responses"]) == 10
    assert body["session_id"] is None

    get_response = client.get(f"/cuestionarios-sus/{body['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["score"] == 50.0


def test_enviar_con_menos_de_10_respuestas_devuelve_422(client: TestClient):
    token = login(client)

    response = client.post(
        "/cuestionarios-sus",
        json={"responses": _neutral_responses()[:9]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_enviar_con_score_fuera_de_rango_devuelve_422(client: TestClient):
    token = login(client)
    responses = _neutral_responses()
    responses[0]["score"] = 6  # invalido, max es 5

    response = client.post(
        "/cuestionarios-sus",
        json={"responses": responses},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_enviar_con_preguntas_repetidas_devuelve_422(client: TestClient):
    token = login(client, email="repetida@example.com")
    responses = _neutral_responses()[:9] + [{"question_number": 1, "score": 3}]

    response = client.post(
        "/cuestionarios-sus",
        json={"responses": responses},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_consultar_cuestionario_ajeno_devuelve_403(client: TestClient):
    token_ana = login(client, email="ana4@example.com")
    created = client.post(
        "/cuestionarios-sus",
        json={"responses": _neutral_responses()},
        headers={"Authorization": f"Bearer {token_ana}"},
    ).json()

    token_beto = login(client, email="beto4@example.com")

    response = client.get(
        f"/cuestionarios-sus/{created['id']}", headers={"Authorization": f"Bearer {token_beto}"}
    )

    assert response.status_code == 403


def test_consultar_cuestionario_inexistente_devuelve_404(client: TestClient):
    token = login(client, email="dario4@example.com")

    response = client.get(
        "/cuestionarios-sus/01a073bd-60bf-7ce7-b9df-47a52acfd7ea",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
