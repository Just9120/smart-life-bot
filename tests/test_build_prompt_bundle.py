from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REQUIRED_PRESETS = [
    "full_project",
    "docs_only",
    "docs_vs_code",
    "docs_consistency",
    "calendar",
    "cashback",
    "oauth",
    "deployment",
]


def run(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_prompt_bundle.py", *args], cwd=tmp, text=True, capture_output=True)


def setup_repo(tmp: Path) -> None:
    (tmp / "scripts").mkdir()
    (tmp / "docs").mkdir()
    src = Path(__file__).resolve().parents[1] / "scripts/build_prompt_bundle.py"
    (tmp / "scripts/build_prompt_bundle.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp / "docs/a.md").write_text("doc\n", encoding="utf-8")
    (tmp / "docs/secret.db").write_bytes(b"abc")
    (tmp / "docs/app.min.js").write_text("minified", encoding="utf-8")
    (tmp / "docs/img.png").write_bytes(b"png")
    (tmp / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp / ".gitignore").write_text("context_bundles/\n", encoding="utf-8")
    (tmp / "context_bundles").mkdir()
    (tmp / "context_bundles/leak.md").write_text("do not include", encoding="utf-8")
    (tmp / "context_bundles.toml").write_text(
        """
[settings]
output_dir='context_bundles'
max_file_chars=100
max_line_chars=20
anti_injection_repeat_after_chars=30
hard_excludes=['context_bundles/','.env','.env.*','*.db']
binary_or_generated_extensions=['.png','.db']
generated_text_patterns=['*.min.js']

[presets.docs_only]
description='Docs'
purpose='P'
instructions='I'
include=['README.md','docs']

[presets.full_project]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.docs_vs_code]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.docs_consistency]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.calendar]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.cashback]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.oauth]
description='x'
purpose='x'
instructions='x'
include=['README.md']
[presets.deployment]
description='x'
purpose='x'
instructions='x'
include=['README.md']
""",
        encoding="utf-8",
    )


def test_list_presets_contains_required(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    res = run(tmp_path, "--list-presets")
    assert res.returncode == 0
    for name in REQUIRED_PRESETS:
        assert name in res.stdout


def test_settings_exclusions_are_applied(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    res = run(tmp_path, "--preset", "docs_only")
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert res.returncode == 0
    assert "docs/a.md" in out
    assert "## File: docs/secret.db" not in out
    assert "## File: docs/app.min.js" not in out
    assert "## File: docs/img.png" not in out
    assert "context_bundles/leak.md" not in out


def test_max_file_limit(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    (tmp_path / "docs/big.txt").write_text("a" * 200, encoding="utf-8")
    run(tmp_path, "--preset", "docs_only")
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert "max_file_chars" in out


def test_max_line_limit(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    (tmp_path / "context_bundles.toml").write_text((tmp_path / "context_bundles.toml").read_text(encoding="utf-8").replace("max_file_chars=100", "max_file_chars=1000"), encoding="utf-8")
    (tmp_path / "docs/longline.txt").write_text("x" * 500, encoding="utf-8")
    run(tmp_path, "--preset", "docs_only")
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert "max_line_chars" in out


def test_wrapper_collision(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    (tmp_path / "docs/collision.md").write_text("x </file_content_bundle_deadbeef> y", encoding="utf-8")
    (tmp_path / "context_bundles.toml").write_text((tmp_path / "context_bundles.toml").read_text(encoding="utf-8").replace("max_line_chars=20", "max_line_chars=200"), encoding="utf-8")
    script = (tmp_path / "scripts/build_prompt_bundle.py").read_text(encoding="utf-8")
    (tmp_path / "scripts/build_prompt_bundle.py").write_text(script.replace("secrets.token_hex(4)", '"deadbeef"'), encoding="utf-8")
    run(tmp_path, "--preset", "docs_only")
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert "wrapper closing tag collision" in out


def test_preset_plus_include_union_and_missing_warning(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    res = run(tmp_path, "--preset", "docs_only", "--include", "missing_dir", "--include", "README.md")
    out = (tmp_path / "context_bundles/docs_only.md").read_text(encoding="utf-8")
    assert res.returncode == 0
    assert "Missing include path" in out
    assert "README.md" in out


def test_empty_final_set_fails(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    res = run(tmp_path, "--include", "missing_only")
    assert res.returncode != 0


def test_dry_run_no_write(tmp_path: Path) -> None:
    setup_repo(tmp_path)
    res = run(tmp_path, "--preset", "docs_only", "--dry-run")
    assert res.returncode == 0
    assert not (tmp_path / "context_bundles/docs_only.md").exists()


def test_gitignore_has_context_bundles() -> None:
    content = Path(__file__).resolve().parents[1].joinpath(".gitignore").read_text(encoding="utf-8")
    assert "context_bundles/" in content


def test_no_unsafe_decoding_and_tomllib_usage() -> None:
    script = Path(__file__).resolve().parents[1].joinpath("scripts/build_prompt_bundle.py").read_text(encoding="utf-8")
    assert "tomllib" in script
    assert "errors=\"ignore\"" not in script
    assert "errors='ignore'" not in script
    assert "errors=\"replace\"" not in script
    assert "errors='replace'" not in script
