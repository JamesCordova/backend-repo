"""Prueba contra una serie CT REAL (no sintetica) -- 5 slices reales,
des-identificados, incluidos localmente por pydicom como parte de su propio
paquete de pruebas (`pydicom.data`), sin depender de red.

Nota sobre por que no es de TCIA: el pendiente original decia "un dataset
abierto (TCIA u otros repositorios medicos open-access)" -- TCIA
especificamente resulto inalcanzable desde este entorno (timeout real,
mientras que otros hosts si respondian, ver notas de la sesion), asi que se
uso esta alternativa: una serie real y des-identificada, ya redistribuida
como parte del propio paquete `pydicom` (mismo criterio del documento de
arquitectura: "no datos propios de pacientes reales sin desidentificar" --
esta serie ya viene desidentificada de origen, `PatientName` es un valor de
prueba tipo "CompressedSamples^..."), sin la fragilidad de un fetch de red en
cada corrida de tests/CI.

Complementa test_simpleitk_volume_processor.py (que usa una serie sintetica
con valores de pixel inventados de antemano, para poder afirmar el HU exacto
esperado) con una serie real cuyos valores de pixel NO se controlan de
antemano -- la unica forma de confirmar que el pipeline funciona con datos
DICOM reales, no solo con el generador propio.
"""

from pathlib import Path

import numpy as np
import pydicom
from pydicom.data import get_testdata_file

from processing.application.use_cases.process_dicom_series import (
    ProcessDicomSeries,
    ProcessDicomSeriesInput,
)
from processing.infrastructure.dicom.simpleitk_volume_processor import SimpleItkVolumeProcessor

# Serie real de 5 slices (Modality=CT, todas comparten SeriesInstanceUID),
# parte de dicomdirtests/98892001/CT5N/ dentro del paquete `pydicom` -- ver
# pydicom/data/test_files/dicomdirtests/README.txt para el origen.
_REAL_SERIES_FILENAMES = ["2062", "2392", "2693", "3023", "3353"]


def _real_series_paths() -> list[Path]:
    return [Path(get_testdata_file(name)) for name in _REAL_SERIES_FILENAMES]


def _expected_hu_slices() -> list[np.ndarray]:
    """HU esperado por slice, calculado nosotros mismos a partir del pixel
    crudo real + RescaleSlope/RescaleIntercept reales del archivo -- no un
    valor inventado de antemano (a diferencia de la serie sintetica)."""
    expected = []
    for path in _real_series_paths():
        ds = pydicom.dcmread(path)
        raw = ds.pixel_array.astype(np.float64)
        expected.append(raw * float(ds.RescaleSlope) + float(ds.RescaleIntercept))
    return expected


def test_load_series_es_una_serie_ct_real_de_5_slices_16x16():
    processor = SimpleItkVolumeProcessor()

    volume = processor.load_series(_real_series_paths())

    assert volume.pixel_array.shape == (5, 16, 16)


def test_load_series_aplica_rescale_correctamente_sobre_datos_reales():
    processor = SimpleItkVolumeProcessor()
    volume = processor.load_series(_real_series_paths())

    expected_slices = _expected_hu_slices()
    actual_slices = [volume.pixel_array[i] for i in range(volume.pixel_array.shape[0])]

    # SimpleITK ordena las slices espacialmente (por ImagePositionPatient),
    # no necesariamente en el mismo orden que los archivos en disco -- se
    # compara como conjunto, no por indice, para no asumir un orden que no
    # se controla.
    for expected in expected_slices:
        assert any(np.allclose(expected, actual) for actual in actual_slices), (
            "no se encontro ninguna slice real con el HU esperado -- "
            "el rescale (slope/intercept) no se aplico como debia"
        )


def test_load_series_respeta_el_spacing_real_del_dicom():
    processor = SimpleItkVolumeProcessor()
    volume = processor.load_series(_real_series_paths())

    # PixelSpacing real = 0.488281mm (x/y); el spacing en z real entre
    # slices (derivado de ImagePositionPatient) coincide con SliceThickness
    # (2.5mm) en este dataset especifico.
    np.testing.assert_allclose(volume.spacing, (2.5, 0.488281, 0.488281), atol=1e-4)


def test_process_dicom_series_completo_corre_sobre_datos_reales():
    """El pipeline completo (normalizar HU + resamplear por nivel de
    detalle) corre de punta a punta sobre una serie real, no solo sobre la
    sintetica -- sin reventar, con salida en el rango [0, 1] esperado tras
    la normalizacion (domain/hounsfield.py)."""
    processor = SimpleItkVolumeProcessor()
    use_case = ProcessDicomSeries(processor)

    result = use_case.execute(ProcessDicomSeriesInput(dicom_paths=_real_series_paths()))

    assert set(result.keys()) == {"preview", "full"}
    for volume in result.values():
        assert volume.pixel_array.ndim == 3
        assert volume.pixel_array.min() >= 0.0
        assert volume.pixel_array.max() <= 1.0
