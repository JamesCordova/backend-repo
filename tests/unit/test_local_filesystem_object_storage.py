"""LocalFilesystemObjectStorage (lado API, async) -- sin containers, sin
red: es un adaptador de disco, `tmp_path` alcanza. Cubre lo mismo que
tests/integration/test_minio_object_storage.py cubre para MinIO (put/exists/
get_stream de punta a punta, incluido offset/length para Range HTTP), mas la
validacion de path traversal que MinIO no necesita (una key de MinIO es un
nombre virtual, nunca un path de filesystem real)."""

import io
from pathlib import Path

import pytest

from infrastructure.storage.local_filesystem_object_storage import (
    InvalidObjectKeyError,
    LocalFilesystemObjectStorage,
)


async def _collect(storage: LocalFilesystemObjectStorage, key: str, offset: int = 0, length: int = 0) -> bytes:
    chunks = [chunk async for chunk in storage.get_stream(key, offset=offset, length=length)]
    return b"".join(chunks)


async def test_put_luego_get_stream_devuelve_los_mismos_bytes(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(str(tmp_path))
    data = b"contenido de prueba, con varios bytes"

    await storage.put("studies/abc/slice1.dcm", io.BytesIO(data), len(data))

    assert await storage.exists("studies/abc/slice1.dcm") is True
    assert await _collect(storage, "studies/abc/slice1.dcm") == data


async def test_exists_false_para_una_key_que_nunca_se_subio(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(str(tmp_path))
    assert await storage.exists("studies/nada/aqui.dcm") is False


async def test_get_stream_respeta_offset_y_length_para_range_http(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(str(tmp_path))
    data = bytes(range(256)) * 4  # 1024 bytes, deterministico
    await storage.put("results/x/full.nii.gz", io.BytesIO(data), len(data))

    partial = await _collect(storage, "results/x/full.nii.gz", offset=10, length=20)
    assert partial == data[10:30]

    tail = await _collect(storage, "results/x/full.nii.gz", offset=1000, length=0)
    assert tail == data[1000:]


async def test_put_crea_los_directorios_intermedios_que_hagan_falta(tmp_path: Path):
    storage = LocalFilesystemObjectStorage(str(tmp_path))
    await storage.put("a/b/c/d.bin", io.BytesIO(b"x"), 1)
    assert (tmp_path / "a" / "b" / "c" / "d.bin").read_bytes() == b"x"


async def test_ensure_bucket_crea_el_directorio_base_si_no_existe(tmp_path: Path):
    base = tmp_path / "no-existe-todavia"
    storage = LocalFilesystemObjectStorage(str(base))
    assert not base.exists()

    storage.ensure_bucket()

    assert base.is_dir()


@pytest.mark.parametrize(
    "key", ["../fuera.txt", "a/../../fuera.txt", "../../etc/passwd", "..", "a/../.."]
)
async def test_una_key_que_intenta_salir_del_directorio_base_se_rechaza(tmp_path: Path, key: str):
    storage = LocalFilesystemObjectStorage(str(tmp_path))

    with pytest.raises(InvalidObjectKeyError):
        await storage.put(key, io.BytesIO(b"x"), 1)

    # exists() no relanza -- devuelve False (ver el adaptador: una key
    # invalida nunca "existe" dentro del directorio base).
    assert await storage.exists(key) is False
