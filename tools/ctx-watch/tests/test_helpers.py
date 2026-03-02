"""
Tests for the pure helper functions in ctx_watch:
  - _fmt_elapsed
  - _timestamp
  - _should_skip
  - _ctx_of
  - _C (color helper class)

These functions are the most composable and testable units in the module.
No I/O, no filesystem, no threads — pure logic.
"""
import re
from pathlib import Path

from ctx_watch import _fmt_elapsed, _timestamp, _should_skip, _ctx_of, _C


# ---------------------------------------------------------------------------
# _fmt_elapsed
# ---------------------------------------------------------------------------

class TestFmtElapsed:
    """
    _fmt_elapsed converts raw seconds into a human-readable string.
    Boundary values are chosen to test every branch of the if-chain.
    """

    def test_zero_seconds(self):
        # Tension: 0 is a valid input (file changed in the same second)
        assert _fmt_elapsed(0) == "0s"

    def test_less_than_minute(self):
        assert _fmt_elapsed(59) == "59s"

    def test_exactly_one_minute(self):
        # Boundary: 60s transitions from the seconds branch to the minutes branch
        assert _fmt_elapsed(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert _fmt_elapsed(90) == "1m 30s"

    def test_exactly_one_hour(self):
        # Boundary: 3600s transitions from minutes to hours branch
        assert _fmt_elapsed(3600) == "1h 0m"

    def test_hours_and_minutes(self):
        assert _fmt_elapsed(3661) == "1h 1m"

    def test_float_is_truncated(self):
        # Fractional seconds must be discarded, not rounded
        assert _fmt_elapsed(59.9) == "59s"

    def test_large_value(self):
        # 7200s = 2h 0m
        assert _fmt_elapsed(7200) == "2h 0m"


# ---------------------------------------------------------------------------
# _timestamp
# ---------------------------------------------------------------------------

class TestTimestamp:
    """
    _timestamp returns a wall-clock string.
    We cannot assert the exact value, but we can assert its format.
    """

    def test_format_matches_hhmmss(self):
        ts = _timestamp()
        # Must match HH:MM:SS
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", ts), f"Unexpected format: {ts!r}"


# ---------------------------------------------------------------------------
# _should_skip
# ---------------------------------------------------------------------------

class TestShouldSkip:
    """
    _should_skip decides whether a path component is in the skip set.
    Architectural choice: skip on any *part* of the path, not just the leaf.
    This means deep files inside a skipped dir are also rejected.
    Trade-off: simple O(n) scan over parts — acceptable because paths are short.
    """

    def test_skip_git_dir(self):
        path = Path("/project/.git/hooks/pre-commit.py")
        assert _should_skip(path, {".git"}) is True

    def test_skip_venv(self):
        path = Path("/project/.venv/lib/python3.11/site.py")
        assert _should_skip(path, {".venv"}) is True

    def test_not_skipped_normal_file(self):
        path = Path("/project/src/main.py")
        assert _should_skip(path, {".git", ".venv", "__pycache__"}) is False

    def test_empty_skip_set_never_skips(self):
        path = Path("/project/.git/config.py")
        assert _should_skip(path, set()) is False

    def test_partial_name_not_matched(self):
        # "git" should NOT match ".git" — exact part comparison
        path = Path("/project/mygit/module.py")
        assert _should_skip(path, {".git"}) is False

    def test_custom_skip_dir(self):
        path = Path("/project/dist/bundle.js")
        assert _should_skip(path, {"dist"}) is True


# ---------------------------------------------------------------------------
# _ctx_of
# ---------------------------------------------------------------------------

class TestCtxOf:
    """
    _ctx_of derives the .ctx companion path from a source path.
    Convention: source.ext -> source.ext.ctx  (double-extension scheme).
    Trade-off: double-extension is unambiguous but verbose.
    """

    def test_python_file(self):
        result = _ctx_of(Path("/project/src/service.py"))
        assert result == Path("/project/src/service.py.ctx")

    def test_javascript_file(self):
        result = _ctx_of(Path("/project/app/index.js"))
        assert result == Path("/project/app/index.js.ctx")

    def test_preserves_parent(self):
        p = Path("/a/b/c/deep.go")
        assert _ctx_of(p).parent == p.parent

    def test_name_is_source_name_plus_ctx(self):
        p = Path("/repo/auth.ts")
        assert _ctx_of(p).name == "auth.ts.ctx"


# ---------------------------------------------------------------------------
# _C (color helper)
# ---------------------------------------------------------------------------

class TestColorHelper:
    """
    _C provides ANSI escape codes or empty strings depending on the `disabled` flag.
    Architectural choice: encapsulate color logic in one object so all output
    paths share the same toggle — no scattered if/else throughout the module.
    """

    def test_colors_enabled_non_empty(self):
        c = _C(disabled=False)
        assert c.y != ""
        assert c.r != ""
        assert c.g != ""
        assert c.c != ""
        assert c.b != ""
        assert c.rst != ""

    def test_colors_disabled_all_empty(self):
        c = _C(disabled=True)
        assert c.y == ""
        assert c.r == ""
        assert c.g == ""
        assert c.c == ""
        assert c.b == ""
        assert c.rst == ""

    def test_ansi_codes_start_with_escape(self):
        c = _C(disabled=False)
        # All color codes must begin with ESC [
        for attr in ("y", "r", "g", "c", "b", "rst"):
            assert getattr(c, attr).startswith("\033["), (
                f"Expected ANSI escape in {attr}"
            )
