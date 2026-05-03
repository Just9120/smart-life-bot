# Context bundles

Local devtool: `scripts/build_prompt_bundle.py` builds reproducible Markdown bundles from selected repo files.

Use for: LLM audits, handoff, docs-vs-code checks, architecture review, and sharing context with models without repo access.

Do not use as an audit engine: the tool only packages files.

## Commands

- `python scripts/build_prompt_bundle.py --list-presets`
- `python scripts/build_prompt_bundle.py --preset docs_only`
- `python scripts/build_prompt_bundle.py --preset docs_vs_code --dry-run`
- `python scripts/build_prompt_bundle.py --include README.md --include docs --output context_bundles/custom.md`

## Presets

- `full_project`
- `docs_only`
- `docs_vs_code`

(Defined in `context_bundles.toml`.)

## Safety and exclusions

- Excludes env/secrets/db/log/cache/venv/build/git internals/generated bundles and common binary/generated files.
- Reads files as strict UTF-8 only; undecodable files are skipped with warnings.
- Oversized files and files with oversized lines are skipped with warnings.
- Repo-local version does **not** fully parse `.gitignore`.
- Generated `context_bundles/*.md` must not be committed.

## Limitations

- Does not audit by itself.
- Bundle can still be large.
- Token estimate is approximate.
- Binary/docx/pdf/xlsx files are skipped.
- Bad preset coverage can produce incomplete context.

## Future work

- Manual GitHub Actions artifact workflow.
- Centralized CLI package.
- Pathspec-based `.gitignore` support.
