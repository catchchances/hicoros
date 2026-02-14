from types import SimpleNamespace

from hicoros import converter


def _base_args():
    return SimpleNamespace(zip=None, json=None, output_dir="./output", password="pw")


def test_resolve_json_filename_list_prefers_zip_json_list(monkeypatch):
    args = _base_args()
    args.zip = "HiZip.zip"

    monkeypatch.setattr(converter.HiZipReader, "extract_json_list", lambda *_: ["a.json", "b.json"])
    monkeypatch.setattr(
        converter.HiZipReader, "extract_json", lambda *_: (_ for _ in ()).throw(RuntimeError("unexpected call"))
    )

    result = converter.resolve_json_filename_list(args)
    assert result == ["a.json", "b.json"]


def test_resolve_json_filename_list_fallback_to_single_zip_json(monkeypatch):
    args = _base_args()
    args.zip = "HiZip.zip"

    monkeypatch.setattr(converter.HiZipReader, "extract_json_list", lambda *_: None)
    monkeypatch.setattr(converter.HiZipReader, "extract_json", lambda *_: "single.json")

    result = converter.resolve_json_filename_list(args)
    assert result == ["single.json"]


def test_resolve_json_filename_list_extracts_from_json_zip_file(monkeypatch):
    args = _base_args()
    args.json = "payload.zip"

    monkeypatch.setattr(converter.zipfile, "is_zipfile", lambda *_: True)
    monkeypatch.setattr(converter.HiZipReader, "extract_json", lambda *_: "from_zip.json")

    result = converter.resolve_json_filename_list(args)
    assert result == ["from_zip.json"]


def test_resolve_json_filename_list_uses_plain_json_path(monkeypatch):
    args = _base_args()
    args.json = "HiJson.json"

    monkeypatch.setattr(converter.zipfile, "is_zipfile", lambda *_: False)

    result = converter.resolve_json_filename_list(args)
    assert result == ["HiJson.json"]


def test_converter_uses_direct_fit_save_function():
    assert callable(converter.save_fit_file)
