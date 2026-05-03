# Context bundles

`scripts/build_prompt_bundle.py` generates reproducible Markdown bundles from selected repository files.

## When to use

- LLM audits and handoff.
- Docs-vs-code checks.
- Architecture and boundary reviews.
- Sharing project context with models that do not have repository access.

## When not to use

- As an autonomous audit engine (it only packages files).
- For binary document analysis (`.pdf/.docx/.xlsx` are skipped).

## Presets

- `full_project`
- `docs_only`
- `docs_vs_code`
- `docs_consistency`
- `calendar`
- `cashback`
- `oauth`
- `deployment`

Preset definitions and project-specific exclusions live in `context_bundles.toml`.

## Common commands

- `python scripts/build_prompt_bundle.py --list-presets`
- `python scripts/build_prompt_bundle.py --preset docs_only`
- `python scripts/build_prompt_bundle.py --preset docs_vs_code --dry-run`
- `python scripts/build_prompt_bundle.py --include README.md --include docs --output context_bundles/custom.md`
- `python scripts/build_prompt_bundle.py --preset full_project --max-bundle-chars 300000`

## Safety and exclusions

- Reads text files using strict UTF-8 only; undecodable files are skipped with warnings.
- Hard skip rules are configured in `settings` inside `context_bundles.toml`:
  - `hard_excludes`
  - `binary_or_generated_extensions`
  - `generated_text_patterns`
  - `max_file_chars` (hard skip)
  - `max_line_chars` (hard skip)
- `--max-bundle-chars` is a soft warning only (no truncation).
- Repo-local version does **not** fully parse `.gitignore`.
- Generated `context_bundles/*.md` must not be committed.

## Working with coding agents

Ask the agent to run this tool first and use the produced bundle as primary context. For narrow tasks, use a focused preset (`calendar`, `cashback`, `oauth`, or `deployment`) plus optional `--include` additions.

## Models without repo access

Generate bundle locally, provide the `.md` file to the model, and include task instructions separately. If bundle is too large, choose a narrower preset.

## Limitations

- Tool does not audit by itself.
- Bundle size may still be large.
- Token estimate is approximate.
- Binary and office/PDF files are skipped.
- Incorrect preset coverage leads to incomplete context.

## Future work

- Manual GitHub Actions artifact workflow.
- Centralized CLI package.
- Pathspec-based `.gitignore` support.
