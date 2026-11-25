import io
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from domain.entities import ProcessingTask, StudyStatus, Volume


def _login(client: TestClient) -> str:
    client.post(
        "/auth/registro",
        json={"name": "Ana", "email": "ana@example.com", "password": "secret123"},
    )
    login = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "secret123"}
    )
    return login.json()["access_token"]


def _crear_estudio(client: TestClient, token: str, name: str = "Torax de prueba") -> dict:
    return client.post(
        "/estudios",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    ).json()


def test_crear_estudio_sin_token_devuelve_401(client: TestClient):
    response = client.post("/estudios", json={"name": "Torax"})

    assert response.status_code == 401


def test_crear_estudio_devuelve_pending_sin_encolar_todavia(client: TestClient, task_queue):
    token = _login(client)

    response = client.post(
        "/estudios", json={"name": "Torax"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert task_queue.enqueued == []  # todavia no se subio ningun archivo


def test_flujo_completo_subir_archivos_confirmar_y_encolar(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    for filename in ("slice_000.dcm", "slice_001.dcm"):
        response = client.put(
            f"/estudios/{study['id']}/archivos/{filename}",
            headers=headers,
            files={"file": (filename, b"contenido-dicom-falso")},
        )
        assert response.status_code == 204

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida",
        json={"filenames": ["slice_000.dcm", "slice_001.dcm"]},
        headers=headers,
    )

    assert response.status_code == 200
    assert len(task_queue.enqueued) == 1
    _study_id, object_keys = task_queue.enqueued[0]
    assert len(object_keys) == 2
    assert all(study["id"] in key for key in object_keys)


def test_confirmar_subida_sin_subir_nada_devuelve_422(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida",
        json={"filenames": ["nunca_subido.dcm"]},
        headers=headers,
    )

    assert response.status_code == 422
    assert task_queue.enqueued == []


def test_subir_archivo_a_estudio_ajeno_devuelve_403(client: TestClient):
    token_ana = _login(client)
    study = _crear_estudio(client, token_ana, name="Torax de Ana")

    client.post(
        "/auth/registro",
        json={"name": "Beto", "email": "beto@example.com", "password": "secret123"},
    )
    token_beto = client.post(
        "/auth/login", json={"email": "beto@example.com", "password": "secret123"}
    ).json()["access_token"]

    response = client.put(
        f"/estudios/{study['id']}/archivos/a.dcm",
        headers={"Authorization": f"Bearer {token_beto}"},
        files={"file": ("a.dcm", b"x")},
    )

    assert response.status_code == 403


def test_listar_estudios_sin_token_devuelve_401(client: TestClient):
    response = client.get("/estudios")

    assert response.status_code == 401


def test_listar_estudios_devuelve_los_de_todos_los_usuarios(client: TestClient):
    # Axial es una biblioteca compartida (datasets abiertos/sinteticos, no
    # datos reales de pacientes) -- cualquier usuario autenticado ve los
    # estudios de todos, no solo los propios.
    token_ana = _login(client)
    _crear_estudio(client, token_ana, name="Torax de Ana")

    client.post(
        "/auth/registro",
        json={"name": "Beto", "email": "beto-list@example.com", "password": "secret123"},
    )
    token_beto = client.post(
        "/auth/login", json={"email": "beto-list@example.com", "password": "secret123"}
    ).json()["access_token"]
    _crear_estudio(client, token_beto, name="Torax de Beto")

    response = client.get("/estudios", headers={"Authorization": f"Bearer {token_ana}"})

    assert response.status_code == 200
    names = {study["name"] for study in response.json()}
    assert names == {"Torax de Ana", "Torax de Beto"}


def test_listar_estudios_sin_ninguno_devuelve_lista_vacia(client: TestClient):
    token = _login(client)

    response = client.get("/estudios", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []


def test_obtener_estudio_sin_token_devuelve_401(client: TestClient):
    response = client.get("/estudios/01a073bd-60bf-7ce7-b9df-47a52acfd7ea")

    assert response.status_code == 401


def test_obtener_estudio_propio(client: TestClient):
    token = _login(client)
    created = _crear_estudio(client, token)

    response = client.get(
        f"/estudios/{created['id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["stage"] is None
    assert response.json()["progress_percent"] is None


def test_obtener_estudio_refleja_el_progreso_real(client: TestClient, processing_task_repository):
    token = _login(client)
    created = _crear_estudio(client, token)
    processing_task_repository.seed(
        ProcessingTask(
            id=UUID(int=500),
            study_id=UUID(created["id"]),
            attempt_number=1,
            status="running",
            stage="resampling",
            progress_percent=70,
            error_message=None,
            started_at=datetime.now(UTC),
            finished_at=None,
        )
    )

    response = client.get(
        f"/estudios/{created['id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["stage"] == "resampling"
    assert response.json()["progress_percent"] == 70


def test_obtener_estudio_fallido_incluye_el_motivo_real_del_error(
    client: TestClient, processing_task_repository
):
    """Antes de esto, error_message se guardaba en Postgres (worker-repo) pero
    nunca llegaba a la respuesta de la API -- un cliente no tenia forma de
    saber POR QUE fallo un estudio, solo que fallo (encontrado probando el
    frontend real contra un archivo DICOM invalido)."""
    token = _login(client)
    created = _crear_estudio(client, token)
    processing_task_repository.seed(
        ProcessingTask(
            id=UUID(int=500),
            study_id=UUID(created["id"]),
            attempt_number=1,
            status="failed",
            stage=None,
            progress_percent=0,
            error_message="DICOM invalido: faltan cosenos de orientacion",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )

    response = client.get(
        f"/estudios/{created['id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["error_message"] == "DICOM invalido: faltan cosenos de orientacion"


def test_cualquier_usuario_puede_consultar_un_estudio_ajeno(client: TestClient):
    # Axial es una biblioteca compartida -- no hay restriccion por dueno.
    token_ana = _login(client)
    created = _crear_estudio(client, token_ana, name="Torax de Ana")

    client.post(
        "/auth/registro",
        json={"name": "Beto", "email": "beto@example.com", "password": "secret123"},
    )
    token_beto = client.post(
        "/auth/login", json={"email": "beto@example.com", "password": "secret123"}
    ).json()["access_token"]

    response = client.get(
        f"/estudios/{created['id']}", headers={"Authorization": f"Bearer {token_beto}"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_obtener_estudio_inexistente_devuelve_404(client: TestClient):
    token = _login(client)

    response = client.get(
        "/estudios/01a073bd-60bf-7ce7-b9df-47a52acfd7ea",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_descargar_volumen_de_estudio_pending_devuelve_409(client: TestClient):
    token = _login(client)
    study = _crear_estudio(client, token)

    response = client.get(
        f"/estudios/{study['id']}/volumen", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 409


async def test_descargar_volumen_cuando_esta_listo(
    client: TestClient, study_repository, volume_repository, object_storage
):
    token = _login(client)
    study = _crear_estudio(client, token)
    study_id = UUID(study["id"])

    # Simula lo que hace worker-repo al terminar: marca ready y registra el
    # volumen -- esta API no tiene forma propia de hacerlo, solo lo consume.
    stored_study = await study_repository.get_by_id(study_id)
    await study_repository.save(replace(stored_study, status=StudyStatus.READY))

    volume = Volume(
        id=UUID(int=999),
        study_id=study_id,
        processing_task_id=UUID(int=1),
        detail_level="full",
        format="npz",
        storage_path=f"results/{study_id}/full.npz",
        size_bytes=8,
        created_at=datetime.now(UTC),
    )
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(b"npz-fake"), 8)

    response = client.get(
        f"/estudios/{study['id']}/volumen", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.content == b"npz-fake"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "8"


async def test_descargar_volumen_con_range_devuelve_206_y_solo_la_porcion_pedida(
    client: TestClient, study_repository, volume_repository, object_storage
):
    token = _login(client)
    study = _crear_estudio(client, token)
    study_id = UUID(study["id"])
    stored_study = await study_repository.get_by_id(study_id)
    await study_repository.save(replace(stored_study, status=StudyStatus.READY))

    contenido = b"0123456789"
    volume = Volume(
        id=UUID(int=999),
        study_id=study_id,
        processing_task_id=UUID(int=1),
        detail_level="full",
        format="npz",
        storage_path=f"results/{study_id}/full.npz",
        size_bytes=len(contenido),
        created_at=datetime.now(UTC),
    )
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(contenido), len(contenido))

    response = client.get(
        f"/estudios/{study['id']}/volumen",
        headers={"Authorization": f"Bearer {token}", "Range": "bytes=2-4"},
    )

    assert response.status_code == 206
    assert response.content == b"234"
    assert response.headers["content-range"] == "bytes 2-4/10"
    assert response.headers["content-length"] == "3"


async def test_descargar_volumen_con_range_invalido_devuelve_416(
    client: TestClient, study_repository, volume_repository, object_storage
):
    token = _login(client)
    study = _crear_estudio(client, token)
    study_id = UUID(study["id"])
    stored_study = await study_repository.get_by_id(study_id)
    await study_repository.save(replace(stored_study, status=StudyStatus.READY))

    contenido = b"0123456789"
    volume = Volume(
        id=UUID(int=999),
        study_id=study_id,
        processing_task_id=UUID(int=1),
        detail_level="full",
        format="npz",
        storage_path=f"results/{study_id}/full.npz",
        size_bytes=len(contenido),
        created_at=datetime.now(UTC),
    )
    volume_repository.seed(volume)
    await object_storage.put(volume.storage_path, io.BytesIO(contenido), len(contenido))

    response = client.get(
        f"/estudios/{study['id']}/volumen",
        headers={"Authorization": f"Bearer {token}", "Range": "bytes=9999-10000"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_flujo_completo_subir_raw_confirmar_y_encolar(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token, name="Volumen raw")
    headers = {"Authorization": f"Bearer {token}"}

    upload_response = client.put(
        f"/estudios/{study['id']}/archivos/volumen.raw",
        headers=headers,
        files={"file": ("volumen.raw", b"x" * 8)},
    )
    assert upload_response.status_code == 204

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "volumen.raw",
            "dims": [2, 2, 2],
            "dtype": "uint8",
            "spacing": [1.0, 1.0, 1.0],
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert len(task_queue.enqueued_raw) == 1
    _study_id, enqueued_key, dims, dtype, spacing, value_range = task_queue.enqueued_raw[0]
    assert study["id"] in enqueued_key
    assert dims == [2, 2, 2]
    assert dtype == "uint8"
    assert spacing == [1.0, 1.0, 1.0]
    assert value_range is None


def test_flujo_completo_subir_raw_con_value_range_declarado(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token, name="Volumen raw HU")
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        f"/estudios/{study['id']}/archivos/volumen.raw",
        headers=headers,
        files={"file": ("volumen.raw", b"x" * 8)},
    )

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "volumen.raw",
            "dims": [2, 2, 2],
            "dtype": "int16",
            "spacing": [1.0, 1.0, 1.0],
            "value_range": [-1000.0, 1000.0],
        },
        headers=headers,
    )

    assert response.status_code == 200
    *_rest, value_range = task_queue.enqueued_raw[0]
    assert value_range == (-1000.0, 1000.0)


def test_confirmar_subida_raw_con_value_range_invertido_devuelve_422(
    client: TestClient, task_queue
):
    token = _login(client)
    study = _crear_estudio(client, token, name="Volumen raw HU")
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        f"/estudios/{study['id']}/archivos/volumen.raw",
        headers=headers,
        files={"file": ("volumen.raw", b"x" * 8)},
    )

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "volumen.raw",
            "dims": [2, 2, 2],
            "dtype": "int16",
            "spacing": [1.0, 1.0, 1.0],
            "value_range": [1000.0, -1000.0],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert task_queue.enqueued_raw == []


def test_confirmar_subida_raw_sin_subir_nada_devuelve_422(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token, name="Volumen raw")

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "nunca_subido.raw",
            "dims": [2, 2, 2],
            "dtype": "uint8",
            "spacing": [1.0, 1.0, 1.0],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert task_queue.enqueued_raw == []


def test_confirmar_subida_raw_con_dtype_invalido_devuelve_422(client: TestClient, task_queue):
    token = _login(client)
    study = _crear_estudio(client, token, name="Volumen raw")
    headers = {"Authorization": f"Bearer {token}"}
    client.put(
        f"/estudios/{study['id']}/archivos/volumen.raw",
        headers=headers,
        files={"file": ("volumen.raw", b"x" * 8)},
    )

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "volumen.raw",
            "dims": [2, 2, 2],
            "dtype": "complex128",
            "spacing": [1.0, 1.0, 1.0],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert task_queue.enqueued_raw == []


def test_confirmar_subida_raw_de_estudio_ajeno_devuelve_403(client: TestClient):
    token_ana = _login(client)
    study = _crear_estudio(client, token_ana, name="Volumen de Ana")

    client.post(
        "/auth/registro",
        json={"name": "Beto", "email": "beto-raw@example.com", "password": "secret123"},
    )
    token_beto = client.post(
        "/auth/login", json={"email": "beto-raw@example.com", "password": "secret123"}
    ).json()["access_token"]

    response = client.post(
        f"/estudios/{study['id']}/confirmar-subida-raw",
        json={
            "filename": "volumen.raw",
            "dims": [2, 2, 2],
            "dtype": "uint8",
            "spacing": [1.0, 1.0, 1.0],
        },
        headers={"Authorization": f"Bearer {token_beto}"},
    )

    assert response.status_code == 403
