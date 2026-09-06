# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run from the source root without installing (`python -m` finds the package via the
current directory, so cwd matters unless the package is installed):

```
python -m constantsgen constants.txt constants.py            # Python output (default)
python -m constantsgen -l php constants.txt constants.php    # PHP output
python -m constantsgen -l latex constants.txt constants.tex  # LaTeX output
```

`./run` regenerates all three outputs from `constants.txt` — a quick end-to-end smoke test.

Install (provides the `generate_constants` console script): `pip install .`
Requires Python 3.9+ (`pyproject.toml`).

There is no test suite, linter config, or CI. `constants.txt` + `example/file.c` +
`example/file.h` are the working fixtures. The generated `constants.{py,php,tex}` are
**gitignored**, so `git diff` will not show output changes — save copies before changing
the parser or a writer and diff by hand:

```
./run && mkdir -p /tmp/before && cp constants.py constants.php constants.tex /tmp/before/
# ...make the change...
./run && for f in constants.py constants.php constants.tex; do diff -u /tmp/before/$f $f; done
```

Worth also checking that the generated Python actually imports (`python -c 'import constants'`);
generation succeeding does not mean the output is valid — see Known sharp edges.

## Architecture

The tool reads a **specification file** (see `constants.txt` for the format and a full example)
that names C-like source files plus which `#define`s and `enum`s to extract, then emits a
constants file in a target language.

Flow (`constantsgen/cli.py:main`):
1. `ConstantsParser(input_file)` parses the spec and immediately reads/scans the referenced
   source files. It takes an **open file object, not a path** — it uses `input_file.name` to
   resolve source-file paths relative to the spec's directory, so a bare `io.StringIO` will not
   work.
2. A writer class from the `writers` dict is instantiated with the parser and its
   `.write(output_file)` is called.

### `constantsparse.py` — the core

`ConstantsParser.__init__` does everything in one pass; there is no separate parse/resolve step
exposed. It builds these attributes, which are the writer-facing API:
- `constant_values: dict[str, str]` — final name → raw value string (values kept as text, never
  evaluated).
- `enum_values: dict[str, dict[str, str]]` — destination enum name → {member name → value}.
  Values here are `str` for explicit enum values and `int` for implicit ones.
- `source_files`, `imported_constants`, `imported_enums` — intermediate; `imported_*` are
  consumed (`.pop`) as matches are found, so leftovers at the end mean "requested but not found"
  and raise `ParseError`. A name found in more than one source file resolves to the first hit.

Everything is plain `dict`, and both the parser and the writers depend on insertion order for
the ordering of the generated output.

Spec sections: `file:`, `constant:`, `enum:`, `manual_prefix:`, `manual:` / `manual_suffix:`.
`manual_prefix` values land in `constant_values` *before* source files are scanned;
`manual`/`manual_suffix` are held aside and appended *after*. Since values are never evaluated,
this ordering matters only in the generated file — it is what lets a suffix value refer by name
to a constant read from a source file (`ALSO_GOES_IN_THE_OUTPUT REASONABLE_CONSTANT + 2` in the
fixture) and be defined after it.

A section header is any line ending in `:`. Unrecognized section names — including
`manual_`-prefixed ones that are not exactly `manual_prefix`/`manual`/`manual_suffix` — are
**silently ignored** along with all their data lines, rather than raising.

C parsing is regex-based (module-level compiled patterns), not a real parser — syntactically
invalid C (e.g. XDR) is fine. The `constants` pattern deliberately keeps a `#define`'s name and
value on one line, so a valueless `#define FOO` matches nothing and is reported as "not found"
if the spec asks for it.

Enum handling covers three shapes:
- all values explicit;
- all values implicit (numbered from 0);
- exactly one explicit value, which must be the first member, with the rest implicit continuing
  from it.

Any other mix of explicit and implicit values raises `ParseError` — two or more explicit values
alongside implicit ones, and also a lone explicit value that is not the first member declared
(the implicit numbering counts up from the explicit value, so it is only correct if that value
really is first). The ordering check compares where `enum_explicit_value` and
`enum_implicit_value` first match a *name* (`match.start(1)`, not `match.start()`, since the
explicit pattern's leading `\s*` reaches back over newlines), so it is defined purely in terms
of what those patterns consider a member — comments and blank lines between members do not
affect it.

Note that within an enum, explicit members are emitted before implicit ones, so for the
explicit-first shape the output order matches the declaration order only because the explicit
member is the one that has to come first anyway.

All malformed-input failures raise `ParseError` (defined in this module) — do not use `assert`
for input validation here (see git history). That includes the explicit value an implicit run
counts up from: it must be an integer literal, since values are never evaluated, and an enum
like `{ N_A = SOME_MACRO, N_B }` is rejected rather than crashing on `int()`.

### Writers — `pythonwriter.py`, `phpwriter.py`, `latexwriter.py`

Each is a standalone class (`PythonWriter`, `PHPWriter`, `LatexWriter`) taking the parser and
exposing `write(out)`. To add a language, add a writer class and register it in the `writers`
dict in `cli.py` (that dict also supplies argparse's `-l` choices, so no other change is needed).
All three emit enums first, then constants.

Enums are only a real construct in the Python output:
- **Python** emits `class <destination_name>(Enum)`, and mangles member names — lowercased with
  everything up through the first `_` stripped (`NV_BOOL` → `bool`; no underscore means the name
  is used whole). The `@unique` decorator is emitted only when `values_are_unique` finds the
  enum's values all distinct; a C enum with aliased values gets a plain `Enum` so the aliases
  survive. Values are compared as integers where they parse as integer literals (so `1` and
  `0x1` collide) and as raw text otherwise — never by evaluating them.
- **PHP** and **LaTeX** ignore the destination enum name entirely and flatten members into
  top-level `define(...)` / `\newcommand` entries under their unmangled source names.
- **LaTeX** strips `_` from command *names* (LaTeX commands cannot contain underscores).

A member renamed by an `enum:` name override is **not** mangled by the Python writer — an
override is used exactly as written, since mangling it would defeat the point of overriding it.
The parser records which destination names came from an override in
`enum_overridden_names: dict[str, set[str]]` (destination enum name → member names), which is
how the writer tells the two apart. LaTeX still strips underscores from overridden names, since
that is a hard constraint of the format rather than a naming convention.

## Known sharp edges

Confirmed against the current code; each is a live trap when editing:

- **LaTeX mangles names but not values.** The fixture generates
  `\newcommand{\ALSOGOESINTHEOUTPUT}{REASONABLE_CONSTANT + 2}`; the underscores in the value
  survive and that is not valid LaTeX.
- **No line-continuation handling.** A `#define` ending in `\` is captured only up to the end of
  that line, backslash included.
- **Function-like macros keep their parameter list in the name.** `#define F(x) ...` is imported
  under the literal name `F(x)`.
- **Enum members must be one per line.** Both member patterns are `re.MULTILINE` and anchored to
  line ends, so a single-line `enum e { A = 1, B = 2 };` matches nothing and fails with
  "enum e has no values". `clean_contents` exists because of that anchoring: anything trailing a
  member — a comment, or leftover whitespace — silently dropped it, so comments and trailing
  whitespace are removed from an enum body before the patterns run. Nothing does the same for
  the rest of a source file, so a trailing comment on a `#define` still lands in its value.
- **The enum pattern is brittle.** It requires a trailing `;` and does not tolerate nested
  braces; a `}` inside a comment or a string in the enum body will also cut it short, since
  comments are only stripped from the body after this pattern has already found its end.
