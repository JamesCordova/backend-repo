"""Contra MinIO real (testcontainers) -- put/exists/get_stream de punta a
punta, el mismo camino que recorre un archivo subido por HTTP en produccion."""

import io
from uuid import uuid4


async def test_put_exists_y_get_stream_redondo_completo(minio_storage):
    key = f"tests/{uuid4()}/slice.dcm"
    contenido = b"contenido-dicom-de-prueba"

    assert await minio_storage.exists(key) is False

    await minio_storage.put(key, io.BytesIO(contenido), len(contenido))

    assert await minio_storage.exists(key) is True
    chunks = [chunk async for chunk in minio_storage.get_stream(key)]
    assert b"".join(chunks) == contenido


async def test_key_inexistente_no_existe(minio_storage):
    assert await minio_storage.exists(f"tests/{uuid4()}/nunca-subido.dcm") is False


async def test_get_stream_con_offset_y_length_trae_solo_esa_porcion(minio_storage):
    """Soporte de HTTP Range (seccion 6.6) -- el cliente de MinIO manda un
    header Range real contra el objeto real, no una simulacion en memoria."""
    key = f"tests/{uuid4()}/volumen.npz"
    contenido = bytes(range(256)) * 4  # 1024 bytes reales

    await minio_storage.put(key, io.BytesIO(contenido), len(contenido))

    chunks = [chunk async for chunk in minio_storage.get_stream(key, offset=10, length=20)]
    assert b"".join(chunks) == contenido[10:30]
