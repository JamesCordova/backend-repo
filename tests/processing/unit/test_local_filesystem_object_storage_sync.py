"""Version sincrona (lado processing) de
tests/unit/test_local_filesystem_object_storage.py -- ver ese archivo para
el porque de este adaptador. Sin containers: es un adaptador de disco,
`tmp_path` alcanza."""

from pathlib import Path

import pytest

from processing.infrastructure.storage.local_filesystem_object_storage import (
    InvalidObjectKeyError,
    LocalFilesystemObjectStorage,
)


def test_upload_from_luego_download_to_redondo_completo(tmp_path: Path):
    base = tmp_path / "store"
    storage = LocalFilesystemObjectStorage(str(base))
    source = tmp_path / "resultado.nii.gz"
    source.write_bytes(b"nifti-bytes-de-prueba")

    storage.upload_from(source, "results/estudio-1/full.nii.gz")

    downloaded = tmp_path / "descargado.nii.gz"
    storage.download_to("results/estudio-1/full.nii.gz", downloaded)
    assert downloaded.read_bytes() == b"nifti-bytes-de-prueba"


def test_upload_from_crea_los_directorios_intermedios_que_hagan_falta(tmp_path: Path):
    base = tmp_path / "store"
    storage = LocalFilesystemObjectStorage(str(base))
    source = tmp_path / "a.bin"
    source.write_bytes(b"x")

    storage.upload_from(source, "raws/estudio-2/volumen.raw")

    assert (base / "raws" / "estudio-2" / "volumen.raw").read_bytes() == b"x"


def test_una_key_que_intenta_salir_del_directorio_base_se_rechaza(tmp_path: Path):
    base = tmp_path / "store"
    storage = LocalFilesystemObjectStorage(str(base))
    source = tmp_path / "a.bin"
    source.write_bytes(b"x")

    with pytest.raises(InvalidObjectKeyError):
        storage.upload_from(source, "../fuera-del-store.bin")

    with pytest.raises(InvalidObjectKeyError):
        storage.download_to("../../etc/passwd", tmp_path / "salida.bin")


def test_api_y_processing_comparten_el_mismo_directorio_ven_los_mismos_archivos(tmp_path: Path):
    """Confirma el punto central del README: al no haber MinIO de por medio,
    lo que sube el lado API (adaptador async) lo puede leer directo el lado
    processing (adaptador sync) -- mismo directorio base, sin red."""
    import asyncio
    import io

    from infrastructure.storage.local_filesystem_object_storage import (
        LocalFilesystemObjectStorage as AsyncLocalFilesystemObjectStorage,
    )

    base = tmp_path / "store"
    api_side = AsyncLocalFilesystemObjectStorage(str(base))
    processing_side = LocalFilesystemObjectStorage(str(base))

    asyncio.run(api_side.put("studies/x/slice1.dcm", io.BytesIO(b"dicom-bytes"), 11))

    downloaded = tmp_path / "slice1.dcm"
    processing_side.download_to("studies/x/slice1.dcm", downloaded)
    assert downloaded.read_bytes() == b"dicom-bytes"
