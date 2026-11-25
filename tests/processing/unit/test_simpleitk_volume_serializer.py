"""Prueba el adaptador real -- no requiere Docker (SimpleITK es una libreria
normal, no un servicio). Escribe un NIfTI real a disco y lo vuelve a leer con
la misma libreria para confirmar que el redondo completo (pixel_array +
spacing) es fiel, no solo que WriteImage no lanza una excepcion.
"""

from pathlib import Path

import numpy as np
import SimpleITK as sitk

from processing.domain.entities import Volume
from processing.infrastructure.dicom.simpleitk_volume_serializer import SimpleItkVolumeSerializer


def test_save_escribe_un_nifti_legible_con_el_mismo_contenido(tmp_path: Path):
    pixel_array = np.arange(2 * 4 * 4, dtype=np.int16).reshape(2, 4, 4) - 1000
    volume = Volume(pixel_array=pixel_array, spacing=(2.0, 0.5, 0.5))
    serializer = SimpleItkVolumeSerializer()
    out_path = tmp_path / "full.nii.gz"

    serializer.save(volume, out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0
    image = sitk.ReadImage(str(out_path))
    np.testing.assert_array_equal(sitk.GetArrayFromImage(image), pixel_array)
    sx, sy, sz = image.GetSpacing()  # SimpleITK da (x, y, z)
    np.testing.assert_allclose((sz, sy, sx), volume.spacing)


def test_save_produce_un_archivo_distinto_por_nivel_de_detalle(tmp_path: Path):
    preview = Volume(pixel_array=np.zeros((2, 2, 2), dtype=np.int16), spacing=(4.0, 4.0, 4.0))
    full = Volume(pixel_array=np.ones((4, 4, 4), dtype=np.int16), spacing=(1.0, 1.0, 1.0))
    serializer = SimpleItkVolumeSerializer()
    preview_path = tmp_path / "preview.nii.gz"
    full_path = tmp_path / "full.nii.gz"

    serializer.save(preview, preview_path)
    serializer.save(full, full_path)

    assert sitk.GetArrayFromImage(sitk.ReadImage(str(preview_path))).shape == (2, 2, 2)
    assert sitk.GetArrayFromImage(sitk.ReadImage(str(full_path))).shape == (4, 4, 4)
