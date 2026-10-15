"""Publish complete render bundles; roll back ordinary write/publish failures."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile

BUNDLE_FILES = {'figure.svg', 'figure-notes.md', 'audit.json', 'request.json',
                'masks.npz', 'figure.png', 'figure.pdf', 'atlas-mask-qa.png'}


@contextmanager
def staged_output(destination):
    destination = Path(destination).absolute()
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError('Output must be a directory, not a symlink or file')
    if destination.exists() and any(p.name not in BUNDLE_FILES or p.is_dir() or p.is_symlink() for p in destination.iterdir()):
        raise ValueError('Use a dedicated render output directory; unrelated files will not be replaced')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.brainmap-stage-', dir=destination.parent) as temp:
        stage = Path(temp)/'bundle';stage.mkdir()
        yield stage
        # Keep a backup outside the auto-cleaned staging tree. If even rollback
        # fails (e.g. permissions change), the previous bundle remains recoverable.
        backup = None
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix='.brainmap-backup-', dir=destination.parent))
            try:
                os.replace(destination, backup/'previous')
            except BaseException:
                backup.rmdir()
                raise
        try:
            os.replace(stage, destination)
        except BaseException:
            if backup is not None:
                try:
                    os.replace(backup/'previous', destination)
                except OSError as error:
                    raise OSError(f'Publish and rollback failed; previous bundle retained at {backup / "previous"}') from error
                backup.rmdir()
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
