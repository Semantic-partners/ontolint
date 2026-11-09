# Developing Ontolint

For using ontolint, see the [readme](readme.md). This is for working on it. How a run is
assembled, and why, is in [`design.md`](design.md): read it before changing how a report is
built.

## Setup

Install [Poetry](https://python-poetry.org/docs/#installation) (`brew install poetry` on a
Mac), then:

```bash
poetry install          # dependencies, plus ontolint itself in editable mode
poetry run ontolint tests/example_pass.ttl
```

`poetry install` puts the `ontolint` and `ontolint-report` commands in the project's
virtualenv, pointing at `src/`, so an edit takes effect on the next run.
`python -m ontolint` works too.

## Layout

```
src/ontolint/            the one package: the API, the CLI and the engine behind both
  __init__.py, api.py    the public API — Config and lint(), nothing else
  cli.py                 the `ontolint` command
  runner.py              one lint run: inference, then every selected check
  registry.py            the checks a run can perform, in order, and selecting them
  config.py              reading .rdf-lint.yml into a run's settings
  loading.py             reading the input files into a Dataset, one graph per file
  checks/                the checks, one module per family
  profiling.py           the profiling metrics, and subclass inference
  report/                Markdown and CTRF reporters, and the CTRF summary command
  dqv.py                 the DQV reporter, and the Violation records checks fill in
  resolution.py          where a vocabulary comes from: local, sibling, bundled, network
  queries.py             loading and running the SPARQL in sparql/
  model.py, terms.py     the result types and RDF term helpers everything shares
  graphutil.py           rdflib helpers with no ontolint knowledge
  sparql/                one query per check or metric (package data)
  vocabularies/          the bundled vocabularies and their DCAT catalog (package data)
action.yml               the GitHub Action
ontology/olq.ttl         the olq: vocabulary the DQV report uses
scripts/                 deprecated shims for the old `scripts/*.py` invocations
tests/                   the test suite; tests/dqv/ doubles as worked report examples
docs/                    the user reference the readme links to
```

The modules are layered, each importing only from those before it in this list:
`graphutil`, `terms` and `queries`; `dqv`; `model` and `resolution`; `checks`; `profiling`,
`report` and `loading`; `config`; `registry`; `runner`; then `cli` and `api`. `checks/__init__.py` is empty on purpose —
see its docstring.

Everything inside the package uses relative imports. Only `Config` and `lint` are public;
`tests/test_api.py` pins that.

## Tests

```bash
poetry run pytest -n auto                 # everything, in parallel, as CI does
poetry run pytest tests/test_labels.py    # one file
poetry run ruff check src/ scripts/ tests/   # CI lints too
```

CI runs the suite on Linux and Windows, on every Python from 3.11 to 3.14.

Tests never touch the network: `tests/conftest.py` blocks sockets, so an unmocked fetch
fails at once. Use a fake `uri_parser` or `imports.local` to test resolution.

Most suites build an inline Turtle string, parse it and assert on the `CheckResult`s that
`run_qa(graph)` returns.

The *reporter* suites work differently: `tests/data/` holds the whole expected output of
each reporter — Markdown, CTRF and DQV — written out as data, for each of three fixture
cases. Changing anything that assembles a report means regenerating those, and
[`design.md`](design.md) covers what each reporter is built from, how the cases are chosen
and what must never reach a stored expectation.

```bash
UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_*.py tests/test_e2e_dqv.py
```

Review the diff before committing it. Reports must be byte-identical between runs over the
same inputs, or no expectation can be pinned; `design.md` lists the rules that keep them so.

The SPARQL that lifts a config file into the report is specified with
[mustrd](https://github.com/Semantic-partners/mustrd) in `tests/rdf-lint-config/`, run by
the same `pytest` command.

## Adding a check

1. Add a `.sparql` file to `src/ontolint/sparql/`; it is loaded automatically. A check
   judged per input rather than over the graph has no query — see
   `check_one_ontology_per_file`.
2. Write a `check_*` function in the right module under `src/ontolint/checks/`. It records
   what it found with `decided()`, `note()` and `tabulate()` and renders nothing.
3. Add it to `CHECKLIST` in `registry.py`.
4. Add its column to `print_qa_table()` in `report/markdown.py`.
5. Add a `DQV_METRICS` entry in `dqv.py`: slug, definition, dimension, severity.
   `tests/test_dqv.py` fails if one is missing.
6. Store structured violations as `dqv.Violation(term, …)` records, passing RDF terms rather
   than strings, so blank nodes are skolemized correctly.
7. Add passing and failing tests, and a row to the check table in the readme.

## Releasing

`poetry build` writes a wheel and an sdist to `dist/`. The wheel carries `sparql/`,
`vocabularies/` and the CTRF template, and declares the `ontolint` and `ontolint-report`
commands. `scripts/consumer_smoke.sh` builds one, installs it into a clean virtualenv and
runs it from outside the repository, which is the only check of what a user actually
installs. CI runs it on Linux and Windows.

A release is cut by pushing a `v` tag; [`RELEASING.md`](RELEASING.md) has the process.

## Backlog

The backlog is managed in a
[GitHub project](https://github.com/orgs/Semantic-partners/projects/3).
