"""
Shared fixtures for ctx-watch tests.

Architectural note: all filesystem interactions are ephemeral — every test
receives an isolated tmp_path. No shared global state, no test ordering
dependency. Mirrors the isolation strategy of ctx-run's conftest.
"""
import sys
import os

# Make ctx_watch importable without an editable install.
# Trade-off: couples test runner to file layout, but avoids requiring
# `pip install -e .` just to run tests.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Basic directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """
    Empty temp directory that represents a project root.
    Used as the base for all file-based scenario fixtures.
    """
    return tmp_path


@pytest.fixture
def synced_pair(tmp_path: Path):
    """
    Source file + ctx companion that is clean for the NORMAL scan (--since mode).

    Invariant: ctx.mtime >= source.mtime → no drift (ctx updated after source save).
    Trade-off: two separate fixtures are needed because the normal and --reverse
    modes have mutually exclusive mtime invariants.
    Returns (source_path, ctx_path).
    """
    src = tmp_path / "service.py"
    ctx = tmp_path / "service.py.ctx"
    src.write_text("def service(): pass\n")
    ctx.write_text("purpose: 'service'\n")
    # ctx touched last → ctx.mtime >= src.mtime → no normal-mode drift
    ctx.touch()
    return src, ctx


@pytest.fixture
def reverse_synced_pair(tmp_path: Path):
    """
    Source file + ctx companion that is clean for the REVERSE scan (--reverse mode).

    Invariant: source.mtime >= ctx.mtime → no reverse drift (source is implemented).
    Returns (source_path, ctx_path).
    """
    src = tmp_path / "service.py"
    ctx = tmp_path / "service.py.ctx"
    ctx.write_text("purpose: 'service'\n")
    src.write_text("def service(): pass\n")
    # source touched last → src.mtime >= ctx.mtime → not "spec ahead of source"
    src.touch()
    return src, ctx


@pytest.fixture
def drifted_pair(tmp_path: Path):
    """
    A source file modified AFTER its .ctx — classic drift scenario.

    Trade-off: we manipulate mtime directly to avoid timing flakiness.
    Returns (source_path, ctx_path).
    """
    src = tmp_path / "handler.py"
    ctx = tmp_path / "handler.py.ctx"
    ctx.write_text("purpose: 'handler'\n")
    src.write_text("def handler(): pass\n")
    # Guarantee source is newer by backdating ctx
    import time
    old_mtime = time.time() - 3600
    os.utime(ctx, (old_mtime, old_mtime))
    return src, ctx


@pytest.fixture
def source_without_ctx(tmp_path: Path) -> Path:
    """Source file with no .ctx companion at all."""
    src = tmp_path / "orphan.py"
    src.write_text("def orphan(): pass\n")
    return src


@pytest.fixture
def ctx_without_source(tmp_path: Path) -> Path:
    """A .ctx file whose source file does not exist yet (intent-first workflow)."""
    ctx = tmp_path / "future.py.ctx"
    ctx.write_text("purpose: 'will be implemented'\n")
    return ctx


@pytest.fixture
def nested_project(tmp_path: Path) -> Path:
    """
    Multi-level directory with a mix of synced, drifted, and missing-ctx files.
    Used by directory-walk tests.
    """
    import time

    # subdir/synced.py + synced.py.ctx (ok)
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "synced.py").write_text("pass\n")
    synced_ctx = sub / "synced.py.ctx"
    synced_ctx.write_text("purpose: ok\n")
    synced_ctx.touch()

    # root/drifted.py + drifted.py.ctx  (ctx older than source)
    (tmp_path / "drifted.py").write_text("pass\n")
    drifted_ctx = tmp_path / "drifted.py.ctx"
    drifted_ctx.write_text("purpose: old\n")
    old = time.time() - 7200
    os.utime(drifted_ctx, (old, old))

    # root/orphan.py  (no .ctx)
    (tmp_path / "orphan.py").write_text("pass\n")

    # .git dir that must be skipped
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "hook.py").write_text("pass\n")

    return tmp_path
