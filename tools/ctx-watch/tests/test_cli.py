"""
CLI integration tests for ctx-watch's `status` subcommand.

`status` is the main testable CLI surface of ctx-watch — it performs a
one-shot scan of a directory and exits with 0 (clean) or 1 (drift found).
`watch` requires a real filesystem observer loop and is integration-tested
separately via the observer mock.

All tests use Click's CliRunner, which captures stdout and the exit code
without spawning a subprocess.  No real watchdog threads are started.

Architectural choice: test the CLI boundary (inputs → outputs → exit codes)
rather than the internal walk algorithm. Internal logic is tested in
test_helpers.py and test_tracker.py.
"""
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from ctx_watch import cli


def run(args: list[str]) -> object:
    """Invoke ctx-watch CLI with CliRunner and return the result."""
    return CliRunner().invoke(cli, args)


# ---------------------------------------------------------------------------
# status — no drift (exit 0)
# ---------------------------------------------------------------------------

class TestStatusNoDrift:
    """
    When all recently modified source files have up-to-date .ctx companions,
    status must exit 0 and print a confirmation message.
    """

    def test_exit_0_when_no_source_files(self, tmp_path):
        # Empty directory → nothing to check → OK
        result = run(["status", str(tmp_path), "--no-color"])
        assert result.exit_code == 0

    def test_exit_0_synced_pair(self, synced_pair, tmp_path):
        src, ctx = synced_pair
        # Use --since large enough to include the fixture files
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert result.exit_code == 0

    def test_ok_message_printed(self, tmp_path):
        result = run(["status", str(tmp_path), "--no-color"])
        assert result.exit_code == 0
        # Must print something reassuring — not crash silently
        assert len(result.output.strip()) > 0


# ---------------------------------------------------------------------------
# status — drift detected (exit 1)
# ---------------------------------------------------------------------------

class TestStatusDriftDetected:
    """
    When source files are newer than their ctx, or ctx is missing,
    status must exit 1 and list the offending files.
    """

    def test_exit_1_missing_ctx(self, source_without_ctx, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert result.exit_code == 1

    def test_exit_1_stale_ctx(self, drifted_pair, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert result.exit_code == 1

    def test_output_lists_drifted_filename(self, source_without_ctx, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert "orphan.py" in result.output

    def test_warning_symbol_in_output(self, source_without_ctx, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert "⚠" in result.output

    def test_stale_reason_printed(self, drifted_pair, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        # Reason must mention ctx being outdated
        assert "ctx" in result.output.lower()


# ---------------------------------------------------------------------------
# status — --since filter
# ---------------------------------------------------------------------------

class TestStatusSinceFilter:
    """
    --since N limits the scan to files modified in the last N seconds.
    Files older than the cutoff are ignored even if their ctx is stale.
    """

    def test_old_source_not_reported_with_short_since(self, tmp_path):
        src = tmp_path / "old.py"
        ctx = tmp_path / "old.py.ctx"
        # Write both files, then backdate them to 2 hours ago
        src.write_text("pass\n")
        ctx.write_text("purpose: old\n")
        old = time.time() - 7200
        os.utime(src, (old, old))
        os.utime(ctx, (old - 100, old - 100))  # ctx even older → drift if included

        # With --since 60  the files are outside the window → no drift reported
        result = run(["status", str(tmp_path), "--since", "60", "--no-color"])
        assert result.exit_code == 0

    def test_recent_source_included_with_large_since(self, source_without_ctx, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# status — --changed-files (CI mode)
# ---------------------------------------------------------------------------

class TestStatusChangedFiles:
    """
    --changed-files accepts an explicit space-separated file list and
    bypasses the mtime filter.  Typically fed from `git diff --name-only`.
    """

    def test_explicit_file_with_ctx_exits_0(self, synced_pair, tmp_path):
        src, ctx = synced_pair
        result = run([
            "status", str(tmp_path),
            "--changed-files", str(src),
            "--no-color",
        ])
        assert result.exit_code == 0

    def test_explicit_file_without_ctx_exits_1(self, source_without_ctx, tmp_path):
        result = run([
            "status", str(tmp_path),
            "--changed-files", str(source_without_ctx),
            "--no-color",
        ])
        assert result.exit_code == 1

    def test_non_watched_extension_skipped(self, tmp_path):
        md = tmp_path / "README.md"
        md.write_text("# docs\n")
        result = run([
            "status", str(tmp_path),
            "--changed-files", str(md),
            "--no-color",
        ])
        # .md is not in DEFAULT_EXTENSIONS → checked=0 → "No drift"
        assert result.exit_code == 0

    def test_relative_path_resolved_against_root(self, synced_pair, tmp_path):
        src, ctx = synced_pair
        rel = src.relative_to(tmp_path)
        result = run([
            "status", str(tmp_path),
            "--changed-files", str(rel),
            "--no-color",
        ])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# status — --reverse (intent-first mode)
# ---------------------------------------------------------------------------

class TestStatusReverse:
    """
    --reverse inverts the scan: find .ctx specs that lack a source file.
    Used in intent-first / BDD workflows where specs are written before code.
    """

    def test_exit_0_when_all_specs_implemented(self, reverse_synced_pair, tmp_path):
        result = run(["status", str(tmp_path), "--reverse", "--no-color"])
        assert result.exit_code == 0


    def test_exit_1_when_source_missing(self, ctx_without_source, tmp_path):
        result = run(["status", str(tmp_path), "--reverse", "--no-color"])
        assert result.exit_code == 1

    def test_missing_source_name_in_output(self, ctx_without_source, tmp_path):
        result = run(["status", str(tmp_path), "--reverse", "--no-color"])
        assert "future.py" in result.output

    def test_intent_arrow_symbol_in_output(self, ctx_without_source, tmp_path):
        result = run(["status", str(tmp_path), "--reverse", "--no-color"])
        assert "→" in result.output

    def test_project_ctx_not_flagged_as_intent(self, tmp_path):
        """
        project.ctx has no supported source extension → must not appear in results.
        Trade-off: we check by extension to avoid false positives on meta-files.
        """
        (tmp_path / "project.ctx").write_text("purpose: meta\n")
        result = run(["status", str(tmp_path), "--reverse", "--no-color"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# status — --ext custom extensions
# ---------------------------------------------------------------------------

class TestStatusCustomExtensions:
    """--ext restricts which file extensions are scanned."""

    def test_only_specified_extension_scanned(self, tmp_path):
        # Create a Python file without .ctx (would be drift for 'py')
        (tmp_path / "main.py").write_text("pass\n")
        # Scan only Ruby files → Python orphan not reported
        result = run(["status", str(tmp_path), "--ext", "rb", "--since", "86400", "--no-color"])
        assert result.exit_code == 0

    def test_custom_extension_matched(self, tmp_path):
        src = tmp_path / "app.rb"
        src.write_text("puts 'hello'\n")
        # No companion .ctx → drift
        result = run(["status", str(tmp_path), "--ext", "rb", "--since", "86400", "--no-color"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# status — --ignore-dir
# ---------------------------------------------------------------------------

class TestStatusIgnoreDir:
    """--ignore-dir adds an extra directory name to the skip list."""

    def test_ignored_dir_files_not_reported(self, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "bundle.py").write_text("pass\n")   # no .ctx → drift if included

        result = run([
            "status", str(tmp_path),
            "--ignore-dir", "dist",
            "--since", "86400",
            "--no-color",
        ])
        assert result.exit_code == 0

    def test_default_skip_dirs_always_excluded(self, nested_project):
        # nested_project has a .git dir with a .py file — must be skipped
        result = run(["status", str(nested_project), "--since", "86400", "--no-color"])
        # .git/hook.py must not appear in output
        assert ".git" not in result.output


# ---------------------------------------------------------------------------
# status — --no-color
# ---------------------------------------------------------------------------

class TestNoColor:
    """--no-color must suppress all ANSI escape sequences."""

    def test_no_ansi_in_output(self, source_without_ctx, tmp_path):
        result = run(["status", str(tmp_path), "--since", "86400", "--no-color"])
        assert "\033[" not in result.output

    def test_color_present_without_flag(self, source_without_ctx, tmp_path):
        """
        Without --no-color the output must contain ANSI escape codes.
        Trade-off: CliRunner strips color by default; we must pass color=True
        to invoke() to preserve them. This is the documented way to test
        Click apps that emit ANSI unconditionally (no isatty() check).
        """
        result = CliRunner().invoke(
            cli,
            ["status", str(tmp_path), "--since", "86400"],
            color=True,
        )
        assert "\033[" in result.output or "\x1b[" in result.output
