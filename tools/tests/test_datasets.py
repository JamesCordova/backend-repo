"""Lectores propios de NRRD y PVM/DDS, y remuestreo isotropico."""

import gzip

import nibabel as nib
import numpy as np
import pytest

from axial_tools.datasets import dds_decode, read_nrrd, read_pvm, resample_isotropic


def _write_nrrd(path, data, header_extra, gz=True):
    sizes = " ".join(str(s) for s in data.shape)
    payload = np.ascontiguousarray(data.transpose(2, 1, 0)).astype("<i2").tobytes()
    if gz:
        payload = gzip.compress(payload)
    head = (f"NRRD0004\ntype: short\ndimension: 3\nsizes: {sizes}\nendian: little\n"
            f"encoding: {'gzip' if gz else 'raw'}\n{header_extra}\n\n").encode()
    path.write_bytes(head + payload)


def test_nrrd_lps_to_ras(tmp_path):
    data = np.arange(4 * 3 * 2, dtype=np.int16).reshape(4, 3, 2)
    _write_nrrd(tmp_path / "v.nrrd", data,
                "space: left-posterior-superior\nspace directions: (0.5,0,0) (0,0.7,0) (0,0,2)\n"
                "space origin: (10,20,30)")
    out, affine = read_nrrd(tmp_path / "v.nrrd")
    np.testing.assert_array_equal(out, data)
    np.testing.assert_allclose(affine[:3, :3], np.diag([-0.5, -0.7, 2]))
    np.testing.assert_allclose(affine[:3, 3], [-10, -20, 30])
    assert "".join(nib.aff2axcodes(affine)) == "LPS"


def test_nrrd_detached_raw(tmp_path):
    data = np.arange(8, dtype=np.int16).reshape(2, 2, 2)
    (tmp_path / "v.raw").write_bytes(np.ascontiguousarray(data.transpose(2, 1, 0)).astype("<i2").tobytes())
    (tmp_path / "v.nhdr").write_text("NRRD0004\ntype: int16\ndimension: 3\nsizes: 2 2 2\nendian: little\n"
                                     "encoding: raw\nspacings: 1 1 1\ndata file: v.raw\n")
    out, _ = read_nrrd(tmp_path / "v.nhdr")
    np.testing.assert_array_equal(out, data)


# --- DDS: codificador minimo segun la especificacion del formato ---------------------------------

class _BitWriter:
    def __init__(self):
        self.bits = []

    def write(self, value, n):
        self.bits += [(value >> (n - 1 - i)) & 1 for i in range(n)]

    def bytes(self):
        bits = self.bits + [0] * (-len(self.bits) % 32)
        words = [int("".join(map(str, bits[i:i + 32])), 2) for i in range(0, len(bits), 32)]
        return np.array(words, dtype=">u4").tobytes()


def _dds_encode(data: bytes, skip=1, block=0) -> bytes:
    arr = np.frombuffer(data, np.uint8)
    if skip > 1:  # des-intercalar (lo que el decodificador revierte)
        chunk = len(arr) if block == 0 else skip * block
        parts = []
        for s in range(0, len(arr), chunk):
            part = arr[s:s + chunk]
            parts += [part[i::skip] for i in range(skip)]
        arr = np.concatenate(parts)
    w = _BitWriter()
    w.write(skip - 1, 2)
    w.write(0, 16)  # strip = 1
    act = 0
    values = arr.tolist()
    for start in range(0, len(values), 127):
        run = values[start:start + 127]
        w.write(len(run), 7)
        w.write(7, 3)  # codigo 7 -> 8 bits
        for v in run:
            delta = ((v - act + 128) % 256) - 128
            w.write(delta + 128, 8)
            act = v
    w.write(0, 7)
    return w.bytes()


@pytest.mark.parametrize("skip,block", [(1, 0), (2, 0), (2, 5)])
def test_dds_roundtrip(skip, block):
    rng = np.random.default_rng(3)
    data = rng.integers(0, 256, 1000, dtype=np.uint8).tobytes()
    assert dds_decode(_dds_encode(data, skip, block), block) == data


def test_pvm_v2_16bit(tmp_path):
    # (k, j, i); PVM de 16 bits es big-endian (ojo: la multiplicacion devuelve orden nativo)
    vol = (np.arange(3 * 2 * 2).reshape(2, 2, 3) * 300).astype(">u2")
    payload = b"PVM2\n3 2 2\n0.5 0.75 2\n2\n" + vol.tobytes() + b"desc\0\0\0\0"
    (tmp_path / "v.pvm").write_bytes(b"DDS v3d\n" + _dds_encode(payload, skip=2))
    data, affine, meta = read_pvm(tmp_path / "v.pvm")
    assert data.shape == (3, 2, 2)
    np.testing.assert_array_equal(data, vol.transpose(2, 1, 0))
    np.testing.assert_allclose(np.diag(affine)[:3], [0.5, 0.75, 2])
    assert meta["descripcion"] == "desc"


def test_resample_isotropic_preserves_extent_and_center():
    data = np.zeros((40, 40, 10), np.float32)
    data[10:30, 10:30, 3:7] = 100
    affine = np.diag([0.5, 0.5, 2.0, 1.0])
    out, new = resample_isotropic(data, affine, 1.0)
    assert out.shape == (20, 20, 20)
    np.testing.assert_allclose(np.linalg.norm(new[:3, :3], axis=0), [1, 1, 1])
    # el centro del volumen en mm no se mueve
    old_c = affine[:3, :3] @ ((np.array(data.shape) - 1) / 2) + affine[:3, 3]
    new_c = new[:3, :3] @ ((np.array(out.shape) - 1) / 2) + new[:3, 3]
    np.testing.assert_allclose(old_c, new_c, atol=1e-6)


def test_write_axial_dicom_roundtrip(tmp_path):
    from axial_tools.datasets import write_axial_dicom
    from axial_tools.reference import read_dicom_series

    rng = np.random.default_rng(5)
    data = rng.integers(-1000, 2000, (6, 5, 4)).astype(np.float32)
    affine = np.diag([-0.8, 0.9, 2.5, 1.0])  # i -> L (no canonico)
    affine[:3, 3] = [10, -20, 30]
    write_axial_dicom(tmp_path, data, affine)
    vol = read_dicom_series(tmp_path)
    a = nib.as_closest_canonical(nib.Nifti1Image(data, affine))
    b = nib.as_closest_canonical(nib.Nifti1Image(vol.data, vol.affine))
    np.testing.assert_array_equal(np.asarray(a.dataobj), np.asarray(b.dataobj))
    np.testing.assert_allclose(a.affine, b.affine, atol=1e-3)
