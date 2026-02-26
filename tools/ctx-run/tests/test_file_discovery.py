"""
Tests for file discovery and loading: collect_ctx_files, load_ctx, resolve_source.
"""
import os
import pytest
import click

from ctx_run import collect_ctx_files, load_ctx, resolve_source


class TestCollectCtxFiles:
    def test_single_ctx_file(self, tmp_path):
        f = tmp_path / "service.py.ctx"
        f.write_text("purpose: test\n")
        result = collect_ctx_files(str(f))
        assert result == [str(f)]

    def test_directory_finds_all_ctx(self, tmp_path):
        (tmp_path / "a.py.ctx").write_text("purpose: a\n")
        (tmp_path / "b.py.ctx").write_text("purpose: b\n")
        (tmp_path / "c.py").write_text("# not a ctx file")
        result = collect_ctx_files(str(tmp_path))
        assert len(result) == 2
        assert all(f.endswith(".ctx") for f in result)

    def test_directory_is_sorted(self, tmp_path):
        (tmp_path / "z.py.ctx").write_text("purpose: z\n")
        (tmp_path / "a.py.ctx").write_text("purpose: a\n")
        (tmp_path / "m.py.ctx").write_text("purpose: m\n")
        result = collect_ctx_files(str(tmp_path))
        assert result == sorted(result)

    def test_directory_recursive(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "root.py.ctx").write_text("purpose: root\n")
        (sub / "nested.py.ctx").write_text("purpose: nested\n")
        result = collect_ctx_files(str(tmp_path))
        assert len(result) == 2

    def test_skip_hidden_directories(self, tmp_path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "hook.py.ctx").write_text("purpose: should be ignored\n")
        (tmp_path / "real.py.ctx").write_text("purpose: real\n")
        result = collect_ctx_files(str(tmp_path))
        assert len(result) == 1
        assert result[0].endswith("real.py.ctx")

    def test_non_ctx_file_raises(self, tmp_path):
        f = tmp_path / "service.py"
        f.write_text("# python file")
        with pytest.raises(click.BadParameter):
            collect_ctx_files(str(f))

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(click.BadParameter):
            collect_ctx_files(str(tmp_path / "nonexistent.ctx"))

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(click.ClickException):
            collect_ctx_files(str(tmp_path))


class TestLoadCtx:
    def test_loads_valid_yaml(self, tmp_path):
        f = tmp_path / "test.py.ctx"
        f.write_text("purpose: 'test'\ntensions:\n  - 'some tension'\n")
        result = load_ctx(str(f))
        assert result["purpose"] == "test"
        assert result["tensions"] == ["some tension"]

    def test_empty_file_returns_empty_dict(self, tmp_path):
        f = tmp_path / "empty.py.ctx"
        f.write_text("")
        result = load_ctx(str(f))
        assert result == {}

    def test_missing_sections_returns_partial(self, tmp_path):
        f = tmp_path / "partial.py.ctx"
        f.write_text("purpose: 'only purpose'\n")
        result = load_ctx(str(f))
        assert result["purpose"] == "only purpose"
        assert "conceptualTests" not in result

    def test_conceptual_tests_parsed(self, tmp_path):
        f = tmp_path / "with_tests.py.ctx"
        f.write_text("""conceptualTests:
  - name: "Test 1"
    steps:
      - action: "do something"
        expect: "something happens"
""")
        result = load_ctx(str(f))
        assert len(result["conceptualTests"]) == 1
        assert result["conceptualTests"][0]["name"] == "Test 1"
        assert len(result["conceptualTests"][0]["steps"]) == 1


class TestResolveSource:
    def test_source_found(self, tmp_path):
        ctx = tmp_path / "service.py.ctx"
        src = tmp_path / "service.py"
        ctx.write_text("purpose: test\n")
        src.write_text("def service(): pass\n")
        source_path, content, warning = resolve_source(str(ctx))
        assert source_path == str(src)
        assert content == "def service(): pass\n"
        assert warning is None

    def test_source_missing_returns_warning(self, tmp_path):
        ctx = tmp_path / "service.py.ctx"
        ctx.write_text("purpose: test\n")
        source_path, content, warning = resolve_source(str(ctx))
        assert source_path == str(tmp_path / "service.py")
        assert content is None
        assert warning is not None
        assert "not found" in warning

    def test_non_ctx_extension_returns_warning(self, tmp_path):
        f = tmp_path / "service.yaml"
        f.write_text("purpose: test\n")
        source_path, content, warning = resolve_source(str(f))
        assert content is None
        assert warning is not None

    def test_source_content_read_correctly(self, tmp_path):
        ctx = tmp_path / "auth.py.ctx"
        src = tmp_path / "auth.py"
        src.write_text("def login(): return True\n")
        ctx.write_text("purpose: auth\n")
        _, content, _ = resolve_source(str(ctx))
        assert "def login" in content
