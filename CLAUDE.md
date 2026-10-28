# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ontolint is an ontology quality assessment tool. It loads RDF ontology files (Turtle, RDF/XML, OWL) into an RDFLib graph, applies iterative RDFS subclass inference, runs a battery of SPARQL queries to detect quality violations, and outputs a Markdown report plus a CTRF JSON file for CI integration.

## Setup

```bash
# Install Poetry (if not installed)
brew install poetry

# Install dependencies
poetry install
```

## Commands

```bash
# Run QA against an ontology file (outputs Markdown to stdout, CTRF JSON to ./ctrf/)
poetry run scripts/ontology_qa.py tests/example_pass.ttl

# Run with exit code 1 if violations found (for CI)
poetry run scripts/ontology_qa.py tests/example_pass.ttl -e --ctrf-dir ctrf

# Profile only (no QA checks)
poetry run scripts/ontology_qa.py tests/example_pass.ttl -p

# Verbose output (lists violating elements per check)
poetry run scripts/ontology_qa.py tests/example_pass.ttl -v

# Aggregate CTRF JSON files into a single Markdown report
poetry run scripts/generate_custom_report.py --ctrf-dir ctrf --template-path templates/ctrf-report.hbs --output-path out/ctrf_report.md
```

```bash
# Run all tests
poetry run pytest

# Run all tests in parallel (as CI does)
poetry run pytest -n auto

# Run only the mustrd SPARQL specs
poetry run pytest tests/mustrd_configuration.ttl

# Run a single test file
poetry run pytest tests/test_labels.py

# Run a single test
poetry run pytest tests/test_labels.py::test_class_without_label_fails

# Regenerate golden DQV reports in tests/dqv/*/expected.ttl after an intended change
UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py

# Run with coverage (HTML report in htmlcov/)
poetry run pytest --cov=scripts --cov-report=html

# Run with coverage summary in terminal
poetry run pytest --cov=scripts --cov-report=term-missing
```

### Test suite

**The four reporter suites** turn on three files in `tests/data/`: the input
`reporters.ttl`, and two expectations written out as data — `reporters_qaresult.py`, the
`QAResult` that linting it produces, and `reporters_report.md`, the Markdown it renders.

- `test_pipeline_lint_to_qaresult.py` asserts lint still produces the stored instance. It is the
  only one that runs the checks, and the only one a check change should break. When a
  check changes on purpose, update the stored instance from the diff it prints.
- `test_pipeline_qaresult_to_ctrf.py` and `test_pipeline_qaresult_to_dqv.py` take the **stored** instance as
  input, so they test the projection alone — a change to what a check finds cannot break
  them, and a reporter bug cannot be blamed on the checks.
- `test_pipeline_lint_to_markdown.py` asserts a lint still renders the stored Markdown. It has to
  run the linter, because Markdown is not a projection of `QAResult` yet (see design.md).
  Its other assertions are not a second expectation — they say why parts of the text must
  hold, so a failure explains itself instead of handing over a 189-line diff.

Verified by sabotage: breaking a check fails only suite 1, breaking the DQV reporter fails
only suite 4, and changing a line of report wording fails only suite 2. Add to `reporters.ttl` rather than starting another fixture — it is
deliberately mixed (passing and failing checks, a blank node as a domain, a duplicate
label, a deprecated class, an isolated class) and needs no network.

Tests live in `tests/` and call `run_qa(graph) -> QAResult` — the clean seam exposed by the refactoring. Each test builds an inline TTL string, parses it into an `rdflib.Graph`, and asserts on the returned `CheckResult` objects (`check.passed`, `check.count`, `check.elements`).

| File | What it covers |
|---|---|
| `test_profiling.py` | `profiling()` — class/property/shape counts, deprecated, vocabularies |
| `test_ontology_metadata.py` | `owl:Ontology` declaration and description checks, and *one file, one ontology* in both directions — a file declaring none, and one declaring several (#97) |
| `test_labels.py` | Missing label checks for classes, properties, NodeShapes, PropertyShapes |
| `test_descriptions.py` | Missing description checks for all four entity types |
| `test_unique_labels.py` | Duplicate label checks for all four entity types |
| `test_structural.py` | Isolated classes, domain/range, unique identifiers, subclass cycles, untyped classes/properties, namespace hijacking |
| `test_dqv.py` | DQV Turtle report — metrics/dimensions, per-check measurements and violations, roll-up, dataset IRIs, minted IRIs |
| `test_olq_vocabulary.py` | `ontology/olq.ttl` defines exactly the `olq:` terms the DQV report emits, each labelled and described, and passes ontolint |
| `test_e2e_dqv.py` | Golden-file DQV tests: each `tests/dqv/<case>/` has input `.ttl` files (plus optional `.rdf-lint.yml`, `args.txt`) and the `expected.ttl` report; regenerate with `UPDATE_GOLDEN=1 poetry run pytest tests/test_e2e_dqv.py` and review the diff |
| `test_vocabularies.py` | Bundled vocabularies: DCAT catalog/README integrity, coverage of rdflib's term lists, offline validation of core terms, `imports.local` override, `imports.ignore` in either key form |
| `rdf-lint-config/*.mustrd.ttl` | [mustrd](https://github.com/Semantic-partners/mustrd) Given-When-Then specs for SPARQL (e.g. `rdf-lint-to-model.rq`), listed in `tests/mustrd_configuration.ttl` and run by `poetry run pytest` (the plugin is enabled in pyproject's `addopts`) against embedded RDFLib |
| `test_pipeline_lint_to_qaresult.py` | **Reporter suite 1 of 4.** Linting `reporters.ttl` still produces the stored `QAResult` — the checks that ran, what each decided, profiling, datasets, configuration |
| `test_pipeline_lint_to_markdown.py` | **Suite 2.** The same input through to stdout — sections, violations, counts agreeing with the result, no blank-node identifiers, byte-identical between runs |
| `test_pipeline_qaresult_to_ctrf.py` | **Suite 3.** The **stored** QAResult projected to CTRF: an entry per check, statuses, summary counts, elements |
| `test_pipeline_qaresult_to_dqv.py` | **Suite 4.** The **stored** QAResult projected to DQV: a measurement per failed check, violations as `sh:ValidationResult`, the conformance roll-up, no blank nodes |
| `test_api.py` | The programmatic API (`ontolint.lint`): dataset naming, per-file vs merged, graph-valued `imports`, check selection, and that caller graphs are never mutated |
| `test_e2e_cli.py` | End-to-end `main()` tests: CTRF output, exit codes, `--profile-only`, `--ctrf-filename` |


`tests/conftest.py` sets `QA_SPARQL_DIR` to an absolute path before any import, so tests work regardless of working directory. Its autouse `no_network` fixture blocks sockets, so tests never fetch from the network: an unmocked fetch fails at once, as offline. Use a fake `uri_parser` or `imports.local` to test resolution.

## Architecture

`design.md` has the shape of a run — the pipeline, the three reporters and their
granularity, what `--per-file` should mean, and why Markdown is not yet a projection of
`QAResult`. Read it before changing how a report is assembled.

### Data flow

1. `ontology_qa.py` loads one or more RDF files/directories into an `rdflib.Dataset` with
   one named graph per file, so which file a triple came from survives the load. It is
   built with `default_union`, so SPARQL, `len()` and `triples()` all read the union and
   a check cannot tell the inputs were separate. Inferred triples get a context of their
   own (`INFERRED_CONTEXT`), since they came from no file. A caller of `ontolint.lint()`
   passes plain graphs, so every seam below accepts either.
2. RDFS subclass inference is applied iteratively via `infer_subclass_relations()` until no new triples are added — this is needed so checks like `isolated_classes` work correctly across the full class hierarchy
3. `profiling()` runs counting queries (class count, shape count, deprecated elements, vocabularies used)
4. Each QA check function runs its SPARQL query and returns four dicts: `metrics` (counts), `violations` (element lists), `test` (bool flags for CTRF), and a `log` string
5. Results are printed as Markdown and written as CTRF JSON to `--ctrf-dir`, and optionally as DQV Turtle to `--dqv-dir` (see *DQV report* below)

### SPARQL query loading

All `.sparql` files in `./sparql/` are loaded at **module import time** into the global `sparql_queries` dict (filename stem → query string). The directory is controlled by the `QA_SPARQL_DIR` environment variable; the default `./sparql` is relative to the working directory, so the script must be run from the repo root (or `QA_SPARQL_DIR` must be set).

### QA check function signature

Every check function follows the same pattern:
```python
def check_*(in_metrics, graph, name, check, c, status, verbose) -> (metrics, violations, log, c, status)
```
- `in_metrics` — profiling metrics dict (read-only context, e.g. class count for normalisation)
- `check` — dictionary key of the QA check being run, e.g. `missing_class_labels` (used for CTRF test results)
- `c` — running QA check counter (incremented and returned)
- `status` — running violation count (incremented on failure and returned)
- Returns separate dicts so `main()` can merge them with `update()`

QA metrics are normalised (0–1) against their totals in `print_qa_table()`; raw counts appear in verbose/detailed output.

### DQV report

`scripts/dqv.py` holds all DQV code and has no dependency on `ontology_qa.py`:
- `Violation` / `Dataset` records, which the checks and `run_qa()` fill in;
- the metric and dimension catalogue (`DQV_METRICS`, `DQV_DIMENSIONS`);
- `build_dqv_graph()` / `write_dqv_report()`, IRI minting under the base URI, and blank-node skolemization (`canonical_bnode_labels()`).

`ontology_qa.py` imports it as `dqv` (`from scripts import dqv`, falling back to `import dqv` when run as a script, since `scripts/` is then on `sys.path`). The CLI flags and `_write_dqv()` stay in `ontology_qa.py`. The report also records the effective configuration: `describe_configuration()` in `ontology_qa.py` builds `dqv.ConfigSetting` records (key, value, origin, reason) from the checklist, the parsed `.rdf-lint.yml` and the ontolint defaults and bundled vocabularies. `run_qa()` stores them on `QAResult.settings`, and `dqv._add_configuration()` writes them as an `olq:Configuration`. `lint_selection(..., rule_reasons)` records why a rule changed a check. The `olq:` vocabulary is defined in `ontology/olq.ttl`.

### Bundled vocabularies

`vocabularies/` holds Turtle copies of the core vocabularies (RDF incl. RDF 1.2 terms, RDFS, OWL, XSD, SHACL, SKOS, Dublin Core, FOAF, VANN, PROV, schema.org, …), catalogued in `vocabularies/catalog.ttl`, a DCAT catalog with one `dcat:Dataset` per vocabulary (namespace via `vann:preferredNamespaceUri`, file via `dcat:distribution`/`dcat:downloadURL`, plus source, licence, version and `skos:changeNote`). `run_qa()` merges them into `imports.local` via `merge_local_imports()`, with the project's own entries winning. So the undefined-terms check validates core-vocabulary terms offline, and owl-imports of them resolves locally. There is no list of trusted namespaces; projects trust a namespace with `imports.ignore`. `imports.ignore`/`imports.local` keys are matched through `iri_key()`, which strips a trailing `#`/`/`. `VOCAB_DIR` is module-relative, and bundled files are parsed once per process (`_parse_bundled`). Provenance, licences and local edits are in `vocabularies/README.md`; `tests/test_vocabularies.py` checks the bundle.

### Programmatic API

`ontolint/` is the public package, and exposes exactly two names: `Config` and
`lint(datasets, config) -> rdflib.Graph`, which takes graphs the caller already holds and
returns the DQV report as a graph (issue #92). Keep that surface small — anything richer
belongs on the engine side, where the CLI can use it too.

**Where the surface is specified.** `ontolint/api.py`'s `__all__` block is the statement of
it; `Config`'s docstring documents every setting; the readme tabulates them. All three are
enforced by `tests/test_api.py`, which pins `__all__`, the package's public names, and
`Config`'s field names and defaults, and fails if a field is missing from either the
docstring or the readme. `Config` is defined in `scripts/ontology_qa.py` (the CLI builds
one too) but its `__module__` is reset to `ontolint` in `api.py`, so `help()`, pickle and
generated docs name the supported import path rather than an implementation module — undo
that once the module is split and `Config` lives in the package.

**One run, two front ends.** `Config` is the single description of a lint run, and
`ontology_qa.lint_graph(graph, names, config, …)` is the single entry point that performs
one: inference, then every selected check. `main()` calls it for each file (or for the
merged graph) and `ontolint.lint()` calls it for each dataset, so neither front end has its
own idea of what a run is. The pieces around it are what differ — the CLI adds file
loading, Markdown, CTRF and exit codes; `lint()` adds graph copying, dataset naming and
`dqv.build_dqv_graph()`. `select_checks()` resolves `Config.checks` the way the config
file's `enable:` list is resolved; the CLI passes its own checklist instead.

`lint()` returns only the graph, so a consumer reads pass/fail from the per-dataset
`ontolint-conformance` measurement (`olq:conforms`, and `dqv:value` for the number of
failed checks). `tests/test_api.py` asserts on that query, so the readme's snippet can't
rot.

**Naming is optional.** `lint()` takes one graph, an iterable of them, or a mapping of
names; `Config.imports` takes a mapping or a plain iterable of vocabularies. An unnamed
dataset is named by the `owl:Ontology` it declares (`api._derive_name`) — which is what it
would be reported under anyway — falling back to `unnamed-<n>` by position, and two
unnamed graphs declaring the same ontology are rejected rather than silently collapsed. An
unkeyed vocabulary is registered under `defined_namespaces()`: its declared ontology IRIs
and the namespace of each subject, deliberately *excluding* the ontology IRI's own
namespace, since `<…/core>` sits in `<…/>` and claiming that would capture every sibling
vocabulary beside it.

**Set-level checks.** Most checks take one graph, but *one file, one ontology* can only be
judged across the inputs, and only *before* they are merged — the union of two identical
`owl:Ontology` declarations is a single triple, so the evidence is gone by the time any
`check_*` runs. `declared_ontology_sources()` builds `{ontology IRI: [source IRIs]}` from
(source, graph) pairs and `duplicate_ontology_iris()` filters it to the clashes; `lint()`
calls both, while the CLI gets the same mapping back from `load_rdf()` (its sixth return value)
and `_write_dqv()` filters it. `dqv.duplicate_ontology_graph()` renders one measurement per
clashing IRI — on the IRI itself, naming the inputs via `olq:relatedResource` — and returns
it as a graph of its own, which `build_dqv_graph()` merges in.

Such a metric has no `CHECKLIST` entry and no `check_*` function, so it is declared as a
module-level tuple (`DQV_DUPLICATE_ONTOLOGY_METRIC`) like `DQV_ROLLUP_METRIC`, leaving
`test_dqv.py`'s CHECKLIST-to-`DQV_METRICS` invariant intact. The *source* of an input is
distinct from its dataset name: an unnamed graph is named after the ontology it declares, so
two inputs declaring the same one would otherwise be reported as the same input twice.

Two things in `scripts/` exist for the API:
- **Graph-valued `imports.local`.** `_parse_local()`, `_is_bundled()` and `_describe_local()`
  accept an `rdflib.Graph` as well as a path, so a caller can supply a dependency vocabulary
  it already holds; `describe_configuration()` records such a setting with no `olq:localFile`.
- **`source_iris`.** `run_qa(source_iris=…)` stores `'sourceIRIs'` in the profiling metrics:
  one IRI per entry of `filesProcessed`, for sources that are not files. `datasets_for()` and
  `check_owl_declaration()` use them (via `source_iris()`) instead of minting a `file:` IRI
  for something that was never on disk. `dqv.dataset_iri()` decides what a caller's name
  becomes: an absolute IRI is used as it stands, anything else is minted under the base.

### Shared graph helpers

`scripts/graphutil.py` holds the rdflib helpers with no ontolint knowledge in them —
`bound_graph(prefixes)` and `copy_namespaces(target, source)` — so `ontology_qa` and `dqv`
can both use them without importing each other. `copy_namespaces` had been written twice
(`load_rdf`'s inner `_bind_namespaces` and `api._bind`); prefixes are not decoration here,
since the hijacking and profiling checks report on what the input declared, and `+=` copies
triples but not bindings. `dqv.REPORT_PREFIXES` lists what the DQV report binds.

### Report generation

`generate_custom_report.py` aggregates all CTRF JSON files from a directory and renders a Markdown report using `templates/ctrf-report.hbs`. The Handlebars rendering (`simple_handlebars_render`) is implemented from scratch with no external dependency — it supports `{{#each}}`, `{{#if}}`, `{{else}}`, and `{{variable}}`.

### Adding a new QA check

1. Add a `.sparql` file to `sparql/` — it will be auto-loaded. A check judged per input
   rather than over the graph has no query: `ontologies_by_source()` reads the Dataset's
   contexts instead (see `check_one_ontology_per_file`)
2. Write a `check_*` function in `ontology_qa.py` following the pattern above
3. Add an entry to `CHECKLIST` (module-level constant, before `run_qa`)
4. Add the column to `print_qa_table()` — the header, the `|--|` row and the cell
5. Add a `DQV_METRICS` entry in `scripts/dqv.py` (metric slug, definition, dimension, severity) — `tests/test_dqv.py` fails if one is missing
6. Store structured violations with `violations[records_key(check)] = [dqv.Violation(term, ...)]` alongside the CTRF string, so the DQV report can list each offending resource. Pass RDF terms (e.g. `row.c`), not strings, so blank nodes are skolemized correctly
7. Add positive and negative tests to the appropriate `tests/test_*.py` file
