from pathlib import Path

import pytest

from src import storage


NAMES = ["air_quality_hourly.csv", "city_summary.csv", "data_quality_report.csv", "etl_run_metadata.json"]


def snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def test_success_replaces_all_outputs_and_cleans_staging(tmp_path):
    for name in NAMES:
        (tmp_path / name).write_text("old")
    outputs = {name: "new " + name for name in NAMES}
    storage.publish_snapshot(tmp_path, outputs)
    assert snapshot(tmp_path) == {name: text.encode() for name, text in outputs.items()}
    assert not list(tmp_path.glob(".snapshot-*"))


def test_temporary_write_failure_preserves_all_previous_outputs(tmp_path, monkeypatch):
    for name in NAMES:
        (tmp_path / name).write_text("old " + name)
    before = snapshot(tmp_path)
    original = Path.write_text

    def fail_second(path, *args, **kwargs):
        if path.name == NAMES[1] and path.parent.name.startswith(".snapshot-"):
            raise OSError("simulated temporary write failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second)
    with pytest.raises(OSError, match="temporary write failure"):
        storage.publish_snapshot(tmp_path, {name: "new" for name in NAMES})
    assert snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".snapshot-*"))


@pytest.mark.parametrize("previous", [False, True])
def test_replacement_failure_rolls_back_and_cleans_staging(tmp_path, monkeypatch, previous):
    if previous:
        for name in NAMES:
            (tmp_path / name).write_text("old " + name)
    before = snapshot(tmp_path)
    original = storage.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replacement failure")
        return original(source, destination)

    monkeypatch.setattr(storage.os, "replace", fail_second)
    with pytest.raises(OSError, match="replacement failure"):
        storage.publish_snapshot(tmp_path, {name: "new" for name in NAMES})
    assert snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".snapshot-*"))
