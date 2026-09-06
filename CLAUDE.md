# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run from a source checkout without installing:

```
python -m constantsgen constants.txt constants.py            # Python output (default)
python -m constantsgen -l php constants.txt constants.php    # PHP output
python -m constantsgen -l latex constants.txt constants.tex  # LaTeX output
```

`./run` regenerates all three outputs from `constants.txt` — a quick end-to-end smoke test.

Install (provides the `generate_constants` console script): `pip install .`

There is no test suite, linter config, or CI. `constants.txt` + `example/file.c` + `example/file.h` are the working fixtures; after changing the parser or a writer, run `./run` and diff the generated files.

## Architecture

The tool reads a **specification file** (see `constants.txt` for the format and a full example) that names C-like source files plus which `#define`s and `enum`s to extract, then emits a constants file in a target language.

Flow (`constantsgen/cli.py:main`):
1. `ConstantsParser(spec_file)` parses the spec and immediately reads/scans the referenced source files.
2. A writer class from the `writers` dict is instantiated with the parser and its `.write(output_file)` is called.

### `constantsparse.py` — the core

`ConstantsParser.__init__` does everything in one pass; there is no separate parse/resolve step exposed. It builds these attributes, which are the writer-facing API:
- `constant_values: dict[str, str]` — final name → raw value string (values kept as text, never evaluated).
- `enum_values: dict[str, dict[str, str]]` — destination enum name → {member name → value string}.
- `source_files`, `imported_constants`, `imported_enums` — intermediate; `imported_*` are consumed (`.pop`) as matches are found, so leftovers at the end mean "requested but not found" and raise `ParseError`.

Spec sections: `file:`, `constant:`, `enum:`, `manual_prefix:`, `manual:` / `manual_suffix:`. `manual_prefix` values land in `constant_values` before source files are scanned (so file values can reference them); `manual`/`manual_suffix` are held aside and appended after (so they can reference file values). Source-file paths in the spec are resolved relative to the spec file's directory.

C parsing is regex-based (module-level compiled patterns), not a real parser — syntactically invalid C (e.g. XDR) is fine. Enum handling supports all-explicit values, all-implicit, or explicit-first-then-implicit; other mixes raise `ParseError`.

All malformed-input failures raise `ParseError` (defined in this module) — do not use `assert` for input validation here (see git history).

### Writers — `pythonwriter.py`, `phpwriter.py`, `latexwriter.py`

Each is a standalone class (`PythonWriter`, `PHPWriter`, `LatexWriter`) taking the parser and exposing `write(out)`. To add a language, add a writer class and register it in the `writers` dict in `cli.py`. Language-specific name mangling lives in the writer:
- Python: enum members are lowercased with everything up to the first `_` stripped (`NV_BOOL` → `bool`).
- LaTeX: `_` stripped from command names (LaTeX commands can't contain underscores).
