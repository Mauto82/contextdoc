"""
Tests for CtxWatchHandler — the watchdog event handler that feeds ChangeTracker.

CtxWatchHandler is the bridge between filesystem events (from watchdog) and
the ChangeTracker session state. It must correctly classify events as:
  - source file modifications → record_source
  - .ctx file saves → record_ctx (and record_intent if source missing)
  - anything in a skipped directory → noop

Architectural choice: we avoid spawning a real watchdog Observer here.
Instead we construct synthetic FileSystemEvent objects and call the handler
methods directly. This makes the suite fast and deterministic.
"""
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from ctx_watch import CtxWatchHandler, ChangeTracker, DEFAULT_EXTENSIONS, SKIP_DIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(path: str, is_dir: bool = False):
    """
    Build a minimal fake watchdog FileSystemEvent.
    We only need src_path and is_directory — the two attributes CtxWatchHandler reads.
    """
    ev = MagicMock()
    ev.src_path = path
    ev.is_directory = is_dir
    return ev


def _make_handler(tmp_path=None, extensions=None, skip_dirs=None):
    """
    Convenience factory for CtxWatchHandler with a real ChangeTracker.
    Returns (handler, tracker) so tests can inspect recorded state.
    """
    tracker = ChangeTracker(grace_period=300)
    ext = extensions if extensions is not None else DEFAULT_EXTENSIONS
    skip = skip_dirs if skip_dirs is not None else SKIP_DIRS
    root = Path(tmp_path) if tmp_path else Path("/tmp/fake-root")
    handler = CtxWatchHandler(tracker, ext, skip, ignore_patterns=[], root=root)
    return handler, tracker


# ---------------------------------------------------------------------------
# Directory events ignored
# ---------------------------------------------------------------------------

class TestDirectoryEventsIgnored:
    """
    CtxWatchHandler must silently ignore directory events.
    Trade-off: watchdog fires on_modified for directories on some platforms;
    we guard against unintended tracker pollution.
    """

    def test_on_modified_directory_ignored(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/pkg", is_dir=True))
        assert tracker.changed_at("/project/pkg") == -1.0

    def test_on_created_directory_ignored(self):
        handler, tracker = _make_handler()
        handler.on_created(_event("/project/pkg", is_dir=True))
        assert tracker.changed_at("/project/pkg") == -1.0


# ---------------------------------------------------------------------------
# Skip-dir enforcement
# ---------------------------------------------------------------------------

class TestSkipDirs:
    """Paths inside skipped directories must never be recorded."""

    def test_git_dir_ignored_on_modified(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/.git/hooks/pre-commit.py"))
        assert tracker.changed_at("/project/.git/hooks/pre-commit.py") == -1.0

    def test_pycache_ignored(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/__pycache__/module.cpython-311.pyc"))
        assert tracker.changed_at("/project/__pycache__/module.cpython-311.pyc") == -1.0

    def test_custom_skip_dir_respected(self):
        handler, tracker = _make_handler(skip_dirs=SKIP_DIRS | {"dist"})
        handler.on_modified(_event("/project/dist/bundle.js"))
        assert tracker.changed_at("/project/dist/bundle.js") == -1.0

    def test_file_outside_skip_dir_recorded(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/src/main.py"))
        assert tracker.changed_at("/project/src/main.py") != -1.0


# ---------------------------------------------------------------------------
# Extension filtering
# ---------------------------------------------------------------------------

class TestExtensionFiltering:
    """Only files whose extension is in the configured set are watched."""

    def test_watched_extension_recorded(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/service.py"))
        assert tracker.changed_at("/project/service.py") != -1.0

    def test_unwatched_extension_ignored(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/README.md"))
        assert tracker.changed_at("/project/README.md") == -1.0

    def test_ts_extension_watched_by_default(self):
        handler, tracker = _make_handler()
        handler.on_modified(_event("/project/app.ts"))
        assert tracker.changed_at("/project/app.ts") != -1.0

    def test_custom_extension_set_honoured(self):
        handler, tracker = _make_handler(extensions={"rb"})
        handler.on_modified(_event("/project/app.rb"))
        handler.on_modified(_event("/project/app.py"))   # py not in custom set
        assert tracker.changed_at("/project/app.rb") != -1.0
        assert tracker.changed_at("/project/app.py") == -1.0


# ---------------------------------------------------------------------------
# .ctx file handling
# ---------------------------------------------------------------------------

class TestCtxFileHandling:
    """
    When a .ctx file is saved the handler must:
    1. Call record_ctx on the *source* path (not the .ctx path).
    2. Optionally call record_intent if the source doesn't exist yet.
    """

    def test_ctx_file_calls_record_ctx_on_source(self, tmp_path):
        handler, tracker = _make_handler()
        src = tmp_path / "service.py"
        src.write_text("pass\n")             # source exists
        ctx = str(tmp_path / "service.py.ctx")

        handler.on_modified(_event(ctx))
        # The *source* path must appear in the updated set
        # (drift_files suppresses a path that is in _ctx_updated)
        assert str(src) in tracker._ctx_updated

    def test_ctx_without_source_records_intent(self, tmp_path):
        handler, tracker = _make_handler()
        ctx = str(tmp_path / "future.py.ctx")
        # future.py does NOT exist

        handler.on_modified(_event(ctx))
        assert str(tmp_path / "future.py") in tracker._intents

    def test_ctx_with_existing_source_no_intent(self, tmp_path):
        handler, tracker = _make_handler()
        src = tmp_path / "service.py"
        src.write_text("pass\n")
        ctx = str(tmp_path / "service.py.ctx")

        handler.on_modified(_event(ctx))
        assert str(src) not in tracker._intents

    def test_ctx_file_not_recorded_as_source(self, tmp_path):
        handler, tracker = _make_handler()
        ctx = str(tmp_path / "service.py.ctx")

        handler.on_modified(_event(ctx))
        # The .ctx path itself must NOT be in source_changes
        assert tracker.changed_at(ctx) == -1.0


# ---------------------------------------------------------------------------
# on_created mirrors on_modified
# ---------------------------------------------------------------------------

class TestOnCreated:
    """
    Editors that write via tmp-file + rename trigger on_created, not on_modified.
    CtxWatchHandler must handle both events identically.
    """

    def test_created_source_recorded(self):
        handler, tracker = _make_handler()
        handler.on_created(_event("/project/new_module.py"))
        assert tracker.changed_at("/project/new_module.py") != -1.0

    def test_created_ctx_recorded_as_ctx_update(self, tmp_path):
        handler, tracker = _make_handler()
        src = tmp_path / "module.py"
        src.write_text("pass\n")
        handler.on_created(_event(str(tmp_path / "module.py.ctx")))
        assert str(src) in tracker._ctx_updated
