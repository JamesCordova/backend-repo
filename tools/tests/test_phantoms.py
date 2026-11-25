"""Los fantasmas tienen la geometria que dicen tener, leidos con las referencias independientes."""

import gzip
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from nibabel.filebasedimages import ImageFileError

from axial_tools import phantoms
from axial_tools.reference import read_dicom_series, read_nifti, read_raw


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("phantoms")
    phantoms.generate(d, nifti_only=False, with_torso_full=False)
    return d


def _centroid_ras(vol, value) -> np.ndarray:
    idx = np.argwhere(vol.data == value).mean(axis=0)
    return vol.world_of(idx)


def test_geometric_dims_spacing_and_sizes(out):
    vol = read_nifti(out / "geometrico_aniso.nii.gz")
    assert vol.data.shape == (286, 286, 80)
    np.testing.assert_allclose(vol.spacing, [0.7, 0.7, 2.5], atol=1e-6)
    assert vol.axcodes == "RAS"
    voxel_mm3 = float(np.prod(vol.spacing))
    sphere = (vol.data == 1000).sum() * voxel_mm3
    cube = (vol.data == 400).sum() * voxel_mm3
    assert sphere == pytest.approx(4 / 3 * np.pi * 40**3, rel=0.03)
    assert cube == pytest.approx(50**3, rel=0.06)
    np.testing.assert_allclose(_centroid_ras(vol, 1000), [50, 0, 0], atol=1.5)


@pytest.mark.parametrize("name,codes", [
    ("marcadores_ras", "RAS"), ("marcadores_lps", "LPS"), ("marcadores_sagital", "PIR"),
])
def test_markers_same_world_position_in_every_storage(out, name, codes):
    vol = read_nifti(out / f"{name}.nii.gz")
    assert vol.axcodes == codes
    np.testing.assert_allclose(_centroid_ras(vol, 800), [60, 0, 0], atol=1.0)   # derecha
    np.testing.assert_allclose(_centroid_ras(vol, 400), [0, 60, 0], atol=1.0)   # anterior
    np.testing.assert_allclose(_centroid_ras(vol, 1500), [0, 0, 60], atol=1.5)  # superior


def test_scl_slope_inter_gives_hu(out):
    img = nib.load(str(out / "nifti_scl.nii.gz"))
    assert img.dataobj.slope == 2.0 and img.dataobj.inter == -1024.0
    ref = read_nifti(out / "geometrico_aniso.nii.gz").data
    np.testing.assert_array_equal(np.asarray(img.get_fdata()), ref)


def test_damaged_niftis_are_damaged(out):
    with pytest.raises(ImageFileError):
        nib.load(str(out / "nifti_cabecera_danada.nii")).get_fdata()
    with pytest.raises((OSError, EOFError, ValueError)):
        nib.load(str(out / "nifti_truncado.nii.gz")).get_fdata()
    with gzip.open(out / "nifti_truncado.nii.gz") as f:
        assert f.read()  # el gzip en si es valido


def test_dicom_axial_matches_nifti(out):
    dcm = read_dicom_series(out / "dicom" / "geometrico_axial")
    nii = read_nifti(out / "geometrico_aniso.nii.gz")
    np.testing.assert_allclose(dcm.spacing, [0.7, 0.7, 2.5], atol=1e-4)
    # DICOM axial (filas -> P, columnas -> L) y NIfTI RAS difieren en el sentido de i y j
    assert dcm.axcodes == "LPS"
    np.testing.assert_array_equal(dcm.data[::-1, ::-1, :], nii.data)


def test_dicom_sagittal_markers_in_place(out):
    dcm = read_dicom_series(out / "dicom" / "marcadores_sagital")
    np.testing.assert_allclose(_centroid_ras(dcm, 800), [60, 0, 0], atol=1.0)
    np.testing.assert_allclose(_centroid_ras(dcm, 400), [0, 60, 0], atol=1.5)
    np.testing.assert_allclose(_centroid_ras(dcm, 1500), [0, 0, 60], atol=2.0)


def test_dicom_defects(out):
    with pytest.raises(ValueError):
        read_dicom_series(out / "dicom" / "mezcla_series")
    import pydicom
    gaps_missing = _gaps(out / "dicom" / "corte_faltante", pydicom)
    assert gaps_missing.max() == pytest.approx(8.0) and np.median(gaps_missing) == pytest.approx(4.0)
    gaps_uneven = _gaps(out / "dicom" / "espaciado_no_uniforme", pydicom)
    assert gaps_uneven.max() == pytest.approx(6.0)
    assert (_gaps(out / "dicom" / "cortes_duplicados", pydicom) == 0).sum() == 1
    assert pydicom.dcmread(next((out / "dicom" / "no_ct").glob("*.dcm"))).Modality == "MR"


def _gaps(folder, pydicom):
    z = sorted(float(pydicom.dcmread(p).ImagePositionPatient[2]) for p in folder.glob("*.dcm"))
    return np.diff(z)


def test_raw_reference_and_defects(out):
    raw = read_raw(out / "raw_geometrico_int16_le.raw", (80, 286, 286), "int16", (2.5, 0.7, 0.7))
    np.testing.assert_array_equal(raw.data, read_nifti(out / "geometrico_aniso.nii.gz").data)
    with pytest.raises(ValueError):
        read_raw(out / "raw_tamano_incorrecto.raw", (80, 286, 286), "int16", (2.5, 0.7, 0.7))
    wrong = read_raw(out / "raw_int16_big_endian.raw", (80, 286, 286), "int16", (2.5, 0.7, 0.7))
    assert wrong.data.min() < -2000 or wrong.data.max() > 5000  # el byte order mal leido sale de rango
