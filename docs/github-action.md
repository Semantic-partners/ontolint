# The Ontolint GitHub Action

Ontolint is published as a composite GitHub Action. No PAT or local setup is required — any
repository in the Semantic Partners organisation can use it directly.

## Minimal setup

Create `.github/workflows/ontolint.yml` in your ontology repository:

```yaml
on: [push, pull_request]

permissions:
  contents: read

jobs:
  ontolint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: Semantic-partners/ontolint@main
        with:
          ontology-paths: ontologies/
```

Replace `ontologies/` with the path to your ontology file or directory (relative to your
repository root). That is all that is required. A ready-to-use workflow is at
[`examples/ci-workflow.yml`](../examples/ci-workflow.yml).

## Checking multiple ontologies

`ontology-paths` accepts any number of files or directories — provide them one per line
using YAML block scalar syntax (`|`):

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: |
      ontologies/core.ttl
      ontologies/shapes.ttl
      ontologies/extras/
```

All paths are loaded into a single combined graph before QA runs, so cross-ontology
references resolve correctly.

To check each file on its own instead — one CTRF file and one report section per ontology —
set `per-file: 'true'`:

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: ontologies/
    per-file: 'true'
```

Each file is then checked as a separate graph. References to the other inputs still resolve,
against those files rather than the network (see
[`imports.siblings`](configuration.md#importssiblings--resolving-against-the-rest-of-the-run)).

When a directory is given, only files with a recognised RDF extension (`.ttl`, `.rdf`,
`.owl`, `.xml`, `.nt`, `.n3`, `.jsonld`, `.trig`, …) are loaded; anything else (READMEs,
configs) is skipped. Any file that is loaded but fails to parse — or an explicitly listed
file that doesn't exist — fails the run with exit code 1, regardless of
`fail-on-violations`. QA is not run against a partially loaded graph.

## Inputs

All inputs are strings (composite action convention). Pass booleans as `'true'` / `'false'`.

| Input | Default | Description |
|---|---|---|
| `ontology-paths` | — | **Required.** One or more paths to ontology files or directories, relative to the repository root. |
| `fail-on-violations` | `'true'` | Exit with code 1 if any check fails, causing the step to fail. |
| `verbose` | `'false'` | List every violating element under each failed check. |
| `profile-only` | `'false'` | Run profiling metrics only; skip all QA checks. |
| `per-file` | `'false'` | Run QA separately on each ontology file (directories expanded) rather than on one merged graph. Produces a CTRF file and report section per file (none when combined with `profile-only`; profiling is only printed to the step log). |
| `config-path` | _(auto-detect)_ | Path to a lint configuration file relative to the repository root. If omitted, the action looks for `.rdf-lint.yml` at the repository root and uses it when present. |
| `dqv` | `'false'` | Also write a [DQV](reports.md#dqv) Turtle report to `ctrf/<dqv-filename>`. It is included in the uploaded artifact and exposed as the `dqv-path` output. |
| `dqv-filename` | `'ontolint-dqv.ttl'` | Filename of the DQV report. |
| `base-uri` | _(`urn:ontolint:`)_ | Namespace under which all DQV instance IRIs are minted: metrics, dimensions, measurements, violations and the assessment. |
| `artifact-name` | `'ontolint-ctrf'` | Name of the uploaded CTRF artifact. Override when invoking the action in multiple jobs of the same run. |

## Outputs

| Output | Description |
|---|---|
| `dqv-path` | Absolute path of the DQV Turtle report, set only when `dqv: 'true'` and the report was written (not in `profile-only` mode, or if no RDF loaded). |

Use it to upload or publish the report in a later step:

```yaml
- uses: Semantic-partners/ontolint@main
  id: ontolint
  with:
    ontology-paths: ontologies/
    per-file: 'true'
    dqv: 'true'
    base-uri: https://example.org/qa/
- run: echo "DQV report at ${{ steps.ontolint.outputs.dqv-path }}"
```

## What it produces

Each run writes a Markdown report to the Actions job summary (visible directly in the GitHub
UI) and uploads a CTRF JSON artifact. Both are published whether the job passes or fails.

The one exception is `per-file: 'true'` combined with `profile-only: 'true'`: no QA checks
run, so no CTRF files or report are produced. There is no job summary or artifact, and the
profiling output appears only in the step log.

## Configuring the checks

Place a `.rdf-lint.yml` at your repository root and the action picks it up; see
[configuration](configuration.md). To use a different location, pass `config-path`:

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: ontologies/
    config-path: config/ontolint.yml
```

## Pinning to a version

For production use, pin to a specific release tag instead of `main`:

```yaml
- uses: Semantic-partners/ontolint@v1
```
