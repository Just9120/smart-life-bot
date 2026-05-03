from __future__ import annotations
import subprocess, sys
from pathlib import Path


def run(tmp: Path, *args: str):
    return subprocess.run([sys.executable, "scripts/build_prompt_bundle.py", *args], cwd=tmp, text=True, capture_output=True)


def base(tmp: Path):
    (tmp / "scripts").mkdir(); (tmp / "docs").mkdir(); (tmp / "context_bundles").mkdir()
    src = Path(__file__).resolve().parents[1] / "scripts/build_prompt_bundle.py"
    (tmp / "scripts/build_prompt_bundle.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp / "context_bundles.toml").write_text("""
[settings]
output_dir='context_bundles'
max_file_chars=100
max_line_chars=20
anti_injection_repeat_after_chars=50
hard_excludes=['context_bundles/','.env','.env.*','*.db']
binary_or_generated_extensions=['.png','.db']
generated_text_patterns=['*.min.js']
[presets.docs_only]
description='d'
purpose='p'
instructions='i'
include=['README.md','docs']
""", encoding="utf-8")
    (tmp / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp / "docs/a.md").write_text("doc\n", encoding="utf-8")


def test_list_presets(tmp_path: Path):
    base(tmp_path); r = run(tmp_path, "--list-presets"); assert r.returncode == 0 and "docs_only" in r.stdout

def test_generate_and_manifest(tmp_path: Path):
    base(tmp_path); r = run(tmp_path, "--preset", "docs_only"); assert r.returncode == 0
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert "## Anti-injection note" in out and "## Included files" in out and "<file_content_bundle_" in out and "## Anti-injection reminder" in out

def test_dry_run(tmp_path: Path):
    base(tmp_path); r = run(tmp_path, "--preset", "docs_only", "--dry-run"); assert r.returncode == 0 and not (tmp_path / "context_bundles/docs_only.md").exists()

def test_unknown_preset(tmp_path: Path):
    base(tmp_path); r = run(tmp_path, "--preset", "x"); assert r.returncode != 0

def test_include_without_preset(tmp_path: Path):
    base(tmp_path); r = run(tmp_path, "--include", "README.md"); assert r.returncode == 0 and (tmp_path / "context_bundles/custom.md").exists()

def test_skips_undecodable_and_binary(tmp_path: Path):
    base(tmp_path); (tmp_path / "docs/bad.bin").write_bytes(b"\xff\xfe\xfd"); (tmp_path / "docs/img.png").write_bytes(b"x")
    r = run(tmp_path, "--preset", "docs_only"); assert r.returncode == 0
    out=(tmp_path / "context_bundles/docs_only.md").read_text(encoding='utf-8'); assert "Skipped" in out
