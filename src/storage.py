"""Publish a small local snapshot after all temporary writes succeed."""

import os
from pathlib import Path
import shutil
import tempfile


def publish_snapshot(directory: Path, outputs: dict[str, str]) -> None:
    """Stage complete outputs and restore the previous files on replacement errors.

    Intended for one local ETL process. Each rename is atomic, but the set of
    renames is not a filesystem transaction: do not read during publication.
    A process kill or unrecoverable filesystem failure requires manual recovery.
    """
    directory.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=directory))
    replaced = []
    preserve_recovery_files = False
    try:
        for name, content in outputs.items():
            (staging / name).write_text(content, encoding="utf-8")
        backup = staging / "previous"
        backup.mkdir()
        for name in outputs:
            if (directory / name).exists():
                shutil.copy2(directory / name, backup / name)
        try:
            for name in outputs:
                os.replace(staging / name, directory / name)
                replaced.append(name)
        except OSError:
            try:
                for name in reversed(replaced):
                    if (backup / name).exists():
                        os.replace(backup / name, directory / name)
                    else:
                        (directory / name).unlink()
            except OSError as recovery_error:
                preserve_recovery_files = True
                raise RuntimeError(
                    f"Snapshot rollback failed; recovery files retained at {staging}"
                ) from recovery_error
            raise
    finally:
        if not preserve_recovery_files:
            shutil.rmtree(staging)
