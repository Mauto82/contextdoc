"""
Git-based drift for `ctx-watch status`.

Inside a git repository drift comes from the history, not from mtimes: a source drifts when
commits after the last commit that touched its .ctx changed it, or when it has uncommitted
changes and its .ctx doesn't. Each test builds a small throwaway repository.
"""
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ctx_watch import cli

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout


def commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def status(repo: Path, *args: str):
    return CliRunner().invoke(cli, ["status", str(repo), "--no-color", *args])


@pytest.fixture
def repo(tmp_path):
    """A repository with app.py and app.py.ctx committed together on main."""
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "app.py.ctx").write_text('purpose: "app"\n')
    commit(tmp_path, "initial")
    return tmp_path


class TestCommittedHistory:
    def test_synced_pair_has_no_drift(self, repo):
        result = status(repo)
        assert result.exit_code == 0
        assert "git history" in result.output

    def test_source_committed_after_ctx_drifts(self, repo):
        (repo / "app.py").write_text("x = 2\n")
        commit(repo, "change source only")
        result = status(repo)
        assert result.exit_code == 1
        assert "app.py" in result.output
        assert "not updated in 1 commit(s)" in result.output

    def test_counts_every_commit_since_the_ctx(self, repo):
        for n in (2, 3):
            (repo / "app.py").write_text(f"x = {n}\n")
            commit(repo, f"change {n}")
        assert "not updated in 2 commit(s)" in status(repo).output

    def test_updating_the_ctx_clears_the_drift(self, repo):
        (repo / "app.py").write_text("x = 2\n")
        commit(repo, "change source")
        (repo / "app.py.ctx").write_text('purpose: "app, reviewed"\n')
        commit(repo, "update ctx")
        assert status(repo).exit_code == 0

    def test_mtimes_are_ignored(self, repo):
        # after a clone or checkout mtimes say nothing: an "older" .ctx must not count as drift
        old = 1_600_000_000
        os.utime(repo / "app.py.ctx", (old, old))
        assert status(repo).exit_code == 0
        # ...while --mtime keeps the old behavior
        assert status(repo, "--mtime", "--since", str(10**10)).exit_code == 1


class TestUncommittedChanges:
    def test_dirty_source_with_clean_ctx_drifts(self, repo):
        (repo / "app.py").write_text("x = 2\n")
        result = status(repo)
        assert result.exit_code == 1
        assert "uncommitted changes" in result.output

    def test_source_and_ctx_edited_together_is_fine(self, repo):
        (repo / "app.py").write_text("x = 2\n")
        (repo / "app.py.ctx").write_text('purpose: "app, reviewed"\n')
        assert status(repo).exit_code == 0

    def test_new_file_without_ctx_is_not_reported_in_a_full_scan(self, repo):
        # a .ctx is expected only where it adds value: a full scan reports drift, not absence
        (repo / "new.py").write_text("y = 1\n")
        assert status(repo).exit_code == 0

    def test_old_committed_file_without_ctx_is_not_reported(self, repo):
        (repo / "legacy.py").write_text("z = 1\n")
        commit(repo, "legacy file, never documented")
        assert status(repo).exit_code == 0


class TestBaseRef:
    def test_only_files_changed_since_base_are_checked(self, repo):
        (repo / "other.py").write_text("o = 1\n")
        commit(repo, "undocumented file on main")
        git(repo, "checkout", "-q", "-b", "feature")
        (repo / "app.py").write_text("x = 2\n")
        commit(repo, "feature change")
        result = status(repo, "--base", "main")
        assert result.exit_code == 1
        assert "app.py" in result.output
        assert "other.py" not in result.output  # unchanged since main: not checked

    def test_new_file_without_ctx_is_reported_with_base(self, repo):
        git(repo, "checkout", "-q", "-b", "feature")
        (repo / "new.py").write_text("y = 1\n")
        commit(repo, "new file")
        result = status(repo, "--base", "main")
        assert result.exit_code == 1
        assert "no .ctx file" in result.output

    def test_clean_branch_passes(self, repo):
        git(repo, "checkout", "-q", "-b", "feature")
        assert status(repo, "--base", "main").exit_code == 0

    def test_base_outside_git_is_an_error(self, tmp_path):
        (tmp_path / "a.py").write_text("a = 1\n")
        assert status(tmp_path, "--base", "main").exit_code == 2
