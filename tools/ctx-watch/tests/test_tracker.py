"""
Tests for ChangeTracker — the stateful core of ctx-watch's watch loop.

ChangeTracker tracks which source files have been modified within a session
and whether their .ctx companions have been updated within the grace period.
These tests exercise all public methods in isolation.

Architectural choice: ChangeTracker is pure Python with no I/O except for
intent_files(), which checks Path.exists(). We use tmp_path fixtures to
control filesystem state when testing intent_files().
"""
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ctx_watch import ChangeTracker


# ---------------------------------------------------------------------------
# record_source / record_ctx
# ---------------------------------------------------------------------------

class TestRecordSource:
    """
    record_source registers a changed file for future drift evaluation.
    Trade-off: storing monotonic time means we cannot easily freeze time;
    we patch time.monotonic in tests that compare elapsed values.
    """

    def test_changed_at_returns_recorded_time(self):
        tracker = ChangeTracker(grace_period=300)
        fake_now = 1000.0
        with patch("ctx_watch.time.monotonic", return_value=fake_now):
            tracker.record_source("/a/b/file.py")
        assert tracker.changed_at("/a/b/file.py") == fake_now

    def test_unknown_path_returns_minus_one(self):
        tracker = ChangeTracker(grace_period=300)
        assert tracker.changed_at("/nonexistent.py") == -1.0

    def test_recording_twice_updates_timestamp(self):
        tracker = ChangeTracker(grace_period=300)
        with patch("ctx_watch.time.monotonic", return_value=100.0):
            tracker.record_source("/file.py")
        with patch("ctx_watch.time.monotonic", return_value=200.0):
            tracker.record_source("/file.py")
        assert tracker.changed_at("/file.py") == 200.0

    def test_record_source_clears_ctx_updated(self):
        """
        Re-saving the source after a ctx update must reset the 'updated' flag.
        Otherwise a stale ctx from a previous cycle would suppress new drift.
        """
        tracker = ChangeTracker(grace_period=0)
        tracker.record_source("/file.py")
        tracker.record_ctx("/file.py")    # ctx updated → no drift

        # Source changed again
        tracker.record_source("/file.py")

        # Grace is 0 → immediately drifted
        with patch("ctx_watch.time.monotonic", return_value=time.monotonic() + 1):
            drifted = list(tracker.drift_files())
        assert any(p == "/file.py" for p, _ in drifted)

    def test_record_source_clears_intent(self):
        """
        When a source file is created, its pending intent must be removed.
        Trade-off: intent and source-change states are separate sets that
        must be kept consistent.
        """
        tracker = ChangeTracker(grace_period=300)
        tracker.record_intent("/file.py")
        tracker.record_source("/file.py")
        # After recording source, intent set must not contain this path
        # (we verify indirectly: intent_files() would yield it only if it's in _intents)
        assert "/file.py" not in tracker._intents


# ---------------------------------------------------------------------------
# drift_files
# ---------------------------------------------------------------------------

class TestDriftFiles:
    """
    drift_files yields (path, elapsed) for files past the grace period
    that have no corresponding ctx update.
    """

    def test_no_changed_files_yields_nothing(self):
        tracker = ChangeTracker(grace_period=300)
        assert list(tracker.drift_files()) == []

    def test_within_grace_period_not_drifted(self):
        tracker = ChangeTracker(grace_period=300)
        with patch("ctx_watch.time.monotonic", return_value=1000.0):
            tracker.record_source("/file.py")
        # Advance time by less than grace_period
        with patch("ctx_watch.time.monotonic", return_value=1200.0):  # +200s < 300
            drifted = list(tracker.drift_files())
        assert drifted == []

    def test_past_grace_period_is_drifted(self):
        tracker = ChangeTracker(grace_period=300)
        with patch("ctx_watch.time.monotonic", return_value=1000.0):
            tracker.record_source("/file.py")
        # Advance time well past grace period
        with patch("ctx_watch.time.monotonic", return_value=1400.0):  # +400s > 300
            drifted = list(tracker.drift_files())
        assert len(drifted) == 1
        path, elapsed = drifted[0]
        assert path == "/file.py"
        assert elapsed == pytest.approx(400.0)

    def test_ctx_updated_suppresses_drift(self):
        tracker = ChangeTracker(grace_period=0)
        with patch("ctx_watch.time.monotonic", return_value=1000.0):
            tracker.record_source("/file.py")
        tracker.record_ctx("/file.py")

        with patch("ctx_watch.time.monotonic", return_value=2000.0):
            drifted = list(tracker.drift_files())
        assert drifted == []

    def test_multiple_files_only_drifted_ones_reported(self):
        tracker = ChangeTracker(grace_period=300)
        with patch("ctx_watch.time.monotonic", return_value=1000.0):
            tracker.record_source("/fast.py")   # will be updated below
            tracker.record_source("/slow.py")

        tracker.record_ctx("/fast.py")          # .ctx updated → no drift

        with patch("ctx_watch.time.monotonic", return_value=1400.0):
            drifted = dict(tracker.drift_files())

        assert "/fast.py" not in drifted
        assert "/slow.py" in drifted

    def test_elapsed_value_is_accurate(self):
        tracker = ChangeTracker(grace_period=0)
        with patch("ctx_watch.time.monotonic", return_value=500.0):
            tracker.record_source("/x.py")
        with patch("ctx_watch.time.monotonic", return_value=750.0):
            results = dict(tracker.drift_files())
        assert results["/x.py"] == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# record_ctx
# ---------------------------------------------------------------------------

class TestRecordCtx:
    """record_ctx marks a source path as having an up-to-date .ctx."""

    def test_ctx_recorded_for_unknown_source(self):
        """
        A .ctx can be saved before the source is modified (intent-first workflow).
        record_ctx must not raise in this case.
        """
        tracker = ChangeTracker(grace_period=300)
        tracker.record_ctx("/future.py")   # source has never been recorded

    def test_multiple_ctx_records_idempotent(self):
        tracker = ChangeTracker(grace_period=300)
        tracker.record_source("/file.py")
        tracker.record_ctx("/file.py")
        tracker.record_ctx("/file.py")   # second call must not corrupt state
        drifted = list(tracker.drift_files())
        assert drifted == []


# ---------------------------------------------------------------------------
# record_intent / intent_files
# ---------------------------------------------------------------------------

class TestIntentFiles:
    """
    intent_files yields source paths where a .ctx exists but the source
    file has not been implemented yet.
    """

    def test_intent_yielded_when_source_missing(self, tmp_path):
        tracker = ChangeTracker(grace_period=300)
        missing = str(tmp_path / "future.py")   # does not exist
        tracker.record_intent(missing)
        intents = list(tracker.intent_files())
        assert missing in intents

    def test_intent_not_yielded_when_source_exists(self, tmp_path):
        tracker = ChangeTracker(grace_period=300)
        src = tmp_path / "exists.py"
        src.write_text("pass\n")
        tracker.record_intent(str(src))   # source actually exists
        intents = list(tracker.intent_files())
        assert str(src) not in intents

    def test_intent_cleared_after_source_created(self, tmp_path):
        """
        If intent_files() finds the source now exists it must auto-remove it.
        This avoids re-reporting the same intent on the next poll cycle.
        """
        tracker = ChangeTracker(grace_period=300)
        src = tmp_path / "late.py"
        tracker.record_intent(str(src))

        # Source file is created between one poll and the next
        src.write_text("pass\n")
        list(tracker.intent_files())      # first call clears it

        # Second call must NOT yield the path again
        intents_again = list(tracker.intent_files())
        assert str(src) not in intents_again

    def test_multiple_intents(self, tmp_path):
        tracker = ChangeTracker(grace_period=300)
        paths = [str(tmp_path / f"f{i}.py") for i in range(3)]
        for p in paths:
            tracker.record_intent(p)
        intents = list(tracker.intent_files())
        assert set(intents) == set(paths)

    def test_empty_when_no_intents_recorded(self):
        tracker = ChangeTracker(grace_period=300)
        assert list(tracker.intent_files()) == []
