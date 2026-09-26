"""Сдаточный пакет: CLI принимает папку или zip, архивы распаковываются во временную папку, вход не меняется."""
import os
import zipfile

from dxaqc.pipeline import _unpack_inputs


def _zip(path, names):
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, b"x")


def test_zip_input_keeps_inner_paths(tmp_path):
    src = tmp_path / "set.zip"
    _zip(src, ["Для теста/a.dcm", "Для теста/b.dcm"])
    work = tmp_path / "work"; work.mkdir()
    root = _unpack_inputs(str(src), str(work))
    found = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
    assert found == ["Для теста/a.dcm", "Для теста/b.dcm"]


def test_folder_without_zip_used_as_is(tmp_path):
    (tmp_path / "in").mkdir(); (tmp_path / "in" / "a.dcm").write_bytes(b"x")
    assert _unpack_inputs(str(tmp_path / "in"), str(tmp_path)) == str(tmp_path / "in")


def test_zip_inside_folder_unpacked_in_place_of_archive(tmp_path):
    inp = tmp_path / "in"; (inp / "p1").mkdir(parents=True)
    (inp / "p1" / "a.dcm").write_bytes(b"x")
    _zip(inp / "p2.zip", ["b.dcm"])
    work = tmp_path / "work"; work.mkdir()
    root = _unpack_inputs(str(inp), str(work))
    found = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
    assert found == ["p1/a.dcm", "p2/b.dcm"]
    assert sorted(os.listdir(inp)) == ["p1", "p2.zip"]
