from fastapi.testclient import TestClient


def login(client: TestClient, email: str = "ana-consent@example.com") -> str:
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": email, "password": "secret123"},
    )
    response = client.post("/auth/login", json={"email": email, "password": "secret123"})
    return response.json()["access_token"]


def test_consultar_consentimiento_sin_token_devuelve_401(client: TestClient):
    response = client.get("/consentimiento")

    assert response.status_code == 401


def test_consultar_antes_de_aceptar_devuelve_accepted_false(client: TestClient):
    token = login(client)

    response = client.get("/consentimiento", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"accepted": False, "accepted_at": None}


def test_aceptar_y_luego_consultar_refleja_la_aceptacion(client: TestClient):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    post_response = client.post("/consentimiento", headers=headers)

    assert post_response.status_code == 201
    body = post_response.json()
    assert body["accepted"] is True
    assert body["accepted_at"] is not None

    get_response = client.get("/consentimiento", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["accepted"] is True
    assert get_response.json()["accepted_at"] == body["accepted_at"]


def test_aceptar_dos_veces_no_cambia_la_fecha_original(client: TestClient):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/consentimiento", headers=headers).json()
    second = client.post("/consentimiento", headers=headers).json()

    assert first["accepted_at"] == second["accepted_at"]


def test_el_consentimiento_de_un_usuario_no_afecta_a_otro(client: TestClient):
    token_ana = login(client, email="ana-consent-2@example.com")
    client.post("/consentimiento", headers={"Authorization": f"Bearer {token_ana}"})

    token_beto = login(client, email="beto-consent@example.com")
    response = client.get("/consentimiento", headers={"Authorization": f"Bearer {token_beto}"})

    assert response.json() == {"accepted": False, "accepted_at": None}
