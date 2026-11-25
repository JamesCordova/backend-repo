from fastapi.testclient import TestClient


def login(client: TestClient, email: str = "ana@example.com") -> str:
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": email, "password": "secret123"},
    )
    response = client.post("/auth/login", json={"email": email, "password": "secret123"})
    return response.json()["access_token"]


def _crear_estudio(client: TestClient, token: str, name: str = "Torax de prueba") -> dict:
    return client.post(
        "/estudios", json={"name": name}, headers={"Authorization": f"Bearer {token}"}
    ).json()


def test_iniciar_sesion_sin_token_devuelve_401(client: TestClient):
    response = client.post("/estudios/01a073bd-60bf-7ce7-b9df-47a52acfd7ea/sesiones")

    assert response.status_code == 401


def test_flujo_completo_sesion_e_interacciones(client: TestClient):
    token = login(client)
    study = _crear_estudio(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    session_response = client.post(f"/estudios/{study['id']}/sesiones", headers=headers)
    assert session_response.status_code == 201
    session = session_response.json()
    assert session["study_id"] == study["id"]
    assert session["ended_at"] is None

    interaction_response = client.post(
        f"/sesiones/{session['id']}/interacciones",
        json={"action_type": "rotar_volumen", "metadata": {"eje": "z", "grados": 90}},
        headers=headers,
    )
    assert interaction_response.status_code == 201
    interaction = interaction_response.json()
    assert interaction["session_id"] == session["id"]
    assert interaction["action_type"] == "rotar_volumen"
    assert interaction["metadata"] == {"eje": "z", "grados": 90}

    end_response = client.post(f"/sesiones/{session['id']}/fin", headers=headers)
    assert end_response.status_code == 204


def test_cualquier_usuario_puede_iniciar_sesion_en_un_estudio_ajeno(client: TestClient):
    # Axial es una biblioteca compartida -- el caso normal es abrir sesion en
    # un estudio que no subio uno mismo.
    token_ana = login(client, email="ana2@example.com")
    study = _crear_estudio(client, token_ana, name="Torax de Ana")

    token_beto = login(client, email="beto2@example.com")

    response = client.post(
        f"/estudios/{study['id']}/sesiones", headers={"Authorization": f"Bearer {token_beto}"}
    )

    assert response.status_code == 201
    assert response.json()["study_id"] == study["id"]


def test_registrar_interaccion_en_sesion_ajena_devuelve_403(client: TestClient):
    token_ana = login(client, email="ana3@example.com")
    study = _crear_estudio(client, token_ana, name="Torax de Ana")
    session = client.post(
        f"/estudios/{study['id']}/sesiones", headers={"Authorization": f"Bearer {token_ana}"}
    ).json()

    token_beto = login(client, email="beto3@example.com")

    response = client.post(
        f"/sesiones/{session['id']}/interacciones",
        json={"action_type": "rotar_volumen", "metadata": {}},
        headers={"Authorization": f"Bearer {token_beto}"},
    )

    assert response.status_code == 403


def test_registrar_interaccion_en_sesion_inexistente_devuelve_404(client: TestClient):
    token = login(client, email="carla@example.com")

    response = client.post(
        "/sesiones/01a073bd-60bf-7ce7-b9df-47a52acfd7ea/interacciones",
        json={"action_type": "rotar_volumen", "metadata": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
