"""Fixtures del lado processing (antes worker-repo). `sys.path` ya tiene
`src/` insertado por tests/conftest.py (raiz, se importa primero) -- solo
hace falta agregar este directorio para poder hacer
`from fixtures.synthetic_dicom import ...` como paquete namespace.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures.synthetic_dicom import write_synthetic_series


@pytest.fixture
def synthetic_dicom_series(tmp_path: Path) -> list[Path]:
    return write_synthetic_series(tmp_path)
