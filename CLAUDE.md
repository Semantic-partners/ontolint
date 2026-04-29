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

# Run a single test file
poetry run pytest tests/test_labels.py

# Run a single test
poetry run pytest tests/test_labels.py::test_class_without_label_fails

# Run with coverage (HTML report in htmlcov/)
poetry run pytest --cov=scripts --cov-report=html

# Run with coverage summary in terminal
poetry run pytest --cov=scripts --cov-report=term-missing
```

### Test suite

Tests live in `tests/` and call `run_qa(graph) -> QAResult` — the clean seam exposed by the refactoring. Each test builds an inline TTL string, parses it into an `rdflib.Graph`, and asserts on the returned `CheckResult` objects (`check.passed`, `check.count`, `check.elements`).

| File | What it covers |
|---|---|
| `test_profiling.py` | `profiling()` — class/property/shape counts, deprecated, vocabularies |
| `test_ontology_metadata.py` | `owl:Ontology` declaration and description checks |
| `test_labels.py` | Missing label checks for classes, properties, NodeShapes, PropertyShapes |
| `test_descriptions.py` | Missing description checks for all four entity types |
| `test_unique_labels.py` | Duplicate label checks for all four entity types |
| `test_structural.py` | Isolated classes, domain/range, unique identifiers, subclass cycles, untyped classes/properties, namespace hijacking |
| `test_integration.py` | End-to-end `main()` tests: CTRF output, exit codes, `--profile-only`, `--ctrf-filename` |

`test_structural.py::test_property_used_without_declaration_fails` is marked `xfail` — it documents a known bug in `sparql/untyped_property.sparql` where `?c` is used in the namespace filter instead of `?p`, causing the check to always return 0 violations.

`tests/conftest.py` sets `QA_SPARQL_DIR` to an absolute path before any import, so tests work regardless of working directory.

## Architecture

### Data flow

1. `ontology_qa.py` loads one or more RDF files/directories into a single `rdflib.Graph`
2. RDFS subclass inference is applied iteratively via `infer_subclass_relations()` until no new triples are added — this is needed so checks like `isolated_classes` work correctly across the full class hierarchy
3. `profiling()` runs counting queries (class count, shape count, deprecated elements, vocabularies used)
4. Each QA check function runs its SPARQL query and returns four dicts: `metrics` (counts), `violations` (element lists), `test` (bool flags for CTRF), and a `log` string
5. Results are printed as Markdown and written as CTRF JSON to `--ctrf-dir`

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

### Report generation

`generate_custom_report.py` aggregates all CTRF JSON files from a directory and renders a Markdown report using `templates/ctrf-report.hbs`. The Handlebars rendering (`simple_handlebars_render`) is implemented from scratch with no external dependency — it supports `{{#each}}`, `{{#if}}`, `{{else}}`, and `{{variable}}`.

### Adding a new QA check

1. Add a `.sparql` file to `sparql/` — it will be auto-loaded
2. Write a `check_*` function in `ontology_qa.py` following the pattern above
3. Add an entry to `TEST_CHECKLIST` (module-level constant, before `run_qa`)
4. Add the metric key to `CHECKS` (module-level constant, after the dataclasses)
5. Add the column to `print_qa_table()`
6. Add positive and negative tests to the appropriate `tests/test_*.py` file
