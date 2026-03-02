#!/usr/bin/env python3
"""ctx-watch: warns when source files change without their .ctx companion being updated."""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── constants ─────────────────────────────────────────────────────────────────

DEFAULT_EXTENSIONS = {"py", "js", "ts", "go", "rb", "java", "rs", "php"}
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache"}

YELLOW = "\033[33m"
RED    = "\033[31m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h {rem // 60}m"


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _ctx_of(source: Path) -> Path:
    return source.parent / (source.name + ".ctx")


# ── change tracker ────────────────────────────────────────────────────────────

class ChangeTracker:
    """Tracks source file changes and .ctx update state within a watch session."""

    def __init__(self, grace_period: int) -> None:
        self.grace_period = grace_period
        self._source_changes: dict[str, float] = {}   # path -> monotonic time
        self._ctx_updated: set[str] = set()            # source paths with updated .ctx

    def record_source(self, path: str) -> None:
        self._source_changes[path] = time.monotonic()
        self._ctx_updated.discard(path)

    def record_ctx(self, source_path: str) -> None:
        self._ctx_updated.add(source_path)

    def changed_at(self, path: str) -> float:
        return self._source_changes.get(path, -1.0)

    def drift_files(self):
        """Yield (source_path, elapsed_seconds) for files past the grace period without a .ctx update."""
        now = time.monotonic()
        for path, changed_at in list(self._source_changes.items()):
            elapsed = now - changed_at
            if elapsed >= self.grace_period and path not in self._ctx_updated:
                yield path, elapsed


# ── watchdog handler ──────────────────────────────────────────────────────────

class CtxWatchHandler(FileSystemEventHandler):
    def __init__(self, tracker: ChangeTracker, extensions: set[str]) -> None:
        self.tracker = tracker
        self.extensions = extensions

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_created(self, event) -> None:
        # Editors that write via tmp+rename trigger created, not modified
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def _handle(self, path: Path) -> None:
        if _should_skip(path):
            return
        name = path.name
        if name.endswith(".ctx"):
            source = path.parent / name[:-4]   # strip trailing .ctx
            self.tracker.record_ctx(str(source))
            return
        ext = path.suffix.lstrip(".")
        if ext in self.extensions:
            self.tracker.record_source(str(path))


# ── color helper ──────────────────────────────────────────────────────────────

class _C:
    def __init__(self, disabled: bool) -> None:
        if disabled:
            self.y = self.r = self.g = self.c = self.b = self.rst = ""
        else:
            self.y   = YELLOW
            self.r   = RED
            self.g   = GREEN
            self.c   = CYAN
            self.b   = BOLD
            self.rst = RESET


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """ctx-watch: monitor .ctx companions for source file drift."""


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--grace", default=300, show_default=True,
              help="Seconds before reporting drift.")
@click.option("--ext", default=None,
              help="Comma-separated extensions to watch (default: py,js,ts,go,rb,java,rs,php).")
@click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
def watch(path: str, grace: int, ext: str | None, no_color: bool) -> None:
    """Watch PATH for source changes without .ctx updates. Blocking (Ctrl+C to stop)."""
    extensions = set(ext.split(",")) if ext else DEFAULT_EXTENSIONS
    c = _C(no_color)
    tracker = ChangeTracker(grace)
    handler = CtxWatchHandler(tracker, extensions)

    observer = Observer()
    observer.schedule(handler, path, recursive=True)
    observer.start()

    ext_display = ",".join(sorted(extensions))
    click.echo(
        f"{c.c}{c.b}ctx-watch{c.rst}: watching {Path(path).resolve()} "
        f"(grace: {grace}s, extensions: {ext_display})"
    )

    # Maps source_path -> monotonic time when last reported.
    # A file re-triggers if its source was modified after the last report.
    reported: dict[str, float] = {}

    try:
        while True:
            time.sleep(5)
            for source_path, elapsed in tracker.drift_files():
                changed_at = tracker.changed_at(source_path)
                if changed_at <= reported.get(source_path, -1.0):
                    continue  # already reported for this modification cycle
                reported[source_path] = time.monotonic()
                ctx = _ctx_of(Path(source_path))
                if ctx.exists():
                    detail = f"{source_path}.ctx not updated ({_fmt_elapsed(elapsed)} ago)"
                else:
                    detail = f"{source_path}.ctx does not exist"
                click.echo(f"[{_timestamp()}] {c.y}⚠{c.rst}  {source_path} — {detail}")
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

    still_drifting = sum(1 for _ in tracker.drift_files())
    if still_drifting:
        noun = "1 file" if still_drifting == 1 else f"{still_drifting} files"
        click.echo(f"\n{c.y}ctx-watch: stopped. {noun} with stale context.{c.rst}")
    else:
        click.echo(f"\n{c.g}ctx-watch: stopped. All .ctx companions up to date.{c.rst}")


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--since", default=3600, show_default=True,
              help="Look back N seconds for recently modified files.")
@click.option("--ext", default=None,
              help="Comma-separated extensions to check.")
@click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
def status(path: str, since: int, ext: str | None, no_color: bool) -> None:
    """One-shot scan of PATH for source files modified without a .ctx update."""
    extensions = set(ext.split(",")) if ext else DEFAULT_EXTENSIONS
    c = _C(no_color)
    root = Path(path).resolve()
    cutoff = time.time() - since
    drift: list[tuple[Path, str]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lstrip(".") not in extensions:
                continue
            try:
                src_mtime = fpath.stat().st_mtime
            except OSError:
                continue
            if src_mtime < cutoff:
                continue
            ctx = _ctx_of(fpath)
            if not ctx.exists():
                drift.append((fpath, "no .ctx file"))
            elif ctx.stat().st_mtime < src_mtime:
                lag = src_mtime - ctx.stat().st_mtime
                drift.append((fpath, f".ctx is {_fmt_elapsed(lag)} older than source"))

    if not drift:
        click.echo(f"{c.g}✓{c.rst}  No drift detected in the last {_fmt_elapsed(since)}.")
        sys.exit(0)

    click.echo(f"{c.y}{len(drift)} file(s) with stale context:{c.rst}")
    for fpath, reason in sorted(drift):
        rel = fpath.relative_to(root) if fpath.is_relative_to(root) else fpath
        click.echo(f"  {c.y}⚠{c.rst}  {rel}  ({reason})")
    sys.exit(1)


if __name__ == "__main__":
    cli()
