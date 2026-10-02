# Ontolint: Ontology Quality Assessment

Get an instant, user-friendly snapshot of your ontology’s size and health, right in your CI pipeline. This tool profiles your ontology file (triples, classes, properties, etc.) and runs quality checks (declarations, descriptions, versioning, structure), then produces a clear report so you can track complexity over time, catch regressions early, and keep your ontology consistently high-quality.

## Usage

We have a [GitHub workflow](/.github/workflows/validate-ontolint.yml) running against two [example ontologies](./tests/) - use this as a reference.

The [`ontology_qa.py`](./scripts/ontology_qa.py) script performs quality assurance on a set of ontologies. It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to check for common ontology quality issues. It reports any violations found in the ontology data.

```
usage: ontology_qa.py [-h] [-e] [-v] [-p] [-i] [--per-file] [--ctrf-dir directory] [--ctrf-filename filename]
                      [--dqv-dir directory] [--dqv-filename filename] [--base-uri uri] [-o filename]
                      [-c path/to/config.yml] [--init]
                      [data_files ...]

A script to perform basic QA on a set of ontologies. It loads RDF files, applies simple RDFS subclass inference, and
runs SPARQL queries to check for common ontology quality issues. It reports any violations found in the ontology data.

positional arguments:
  data_files            List of RDF files or folders to process.

options:
  -h, --help            Show this help message and exit.
  -e, --exit-status     Report an exit status to determine if one or more violations were detected.
  -v, --verbose         Enable verbose output.
  -p, --profile-only    Compute only the profiling metrics and skip the QA part.
  -i, --inference       Enable inference of subclass relations before running QA checks. (default: False)
  --per-file            Run QA independently on each input file and produce a separate report per file.
  --ctrf-dir directory  Directory to write CTRF report to.
  --ctrf-filename filename
                        Filename for CTRF report (if None, uses default pattern). Ignored with --per-file.
  --dqv-dir directory   Directory to write a DQV (W3C Data Quality Vocabulary) Turtle report to. Setting this or
                        --dqv-filename enables DQV output.
  --dqv-filename filename
                        Filename for the DQV report (default: ontolint-dqv.ttl). With --per-file, all files are
                        written to this one report.
  --base-uri uri        Namespace under which DQV instance IRIs (metrics, dimensions, measurements, violations,
                        assessment) are minted (default: urn:ontolint:).
  -o filename, --output filename
                        Output file name (optional). If omitted, print to stdout. Ignored with --per-file.
  -c path/to/config.yml, --config path/to/config.yml
                        Path to a YAML configuration file to enable or disable individual checks. Note that if the
                        current directory contains a .rdf-lint.yml file, it will be used by default.
  --init                Generate a default .rdf-lint.yml config file in the current directory.
```

The `generate_custom_report.py` script generates a custom markdown report from aggregated CTRF JSON files. Uses Handlebars template to render the report.

```
usage: generate_custom_report.py [-h] [--ctrf-dir directory] [--template-path directory] [--output-path directory]

optional arguments:
  -h, --help            show this help message and exit
  --ctrf-dir directory  Directory to write CTRF report to.
  --template-path directory
                        Path to the CTRF report template file.
  --output-path directory
                        Path to write the CTRF markdown report file.
```

### DQV report

Pass `--dqv-dir` (and optionally `--dqv-filename`, default `ontolint-dqv.ttl`) to also write the results as a [W3C Data Quality Vocabulary](https://www.w3.org/TR/vocab-dqv/) Turtle file. Unlike the CTRF JSON, every violation is its own node, attributed to the check that raised it and the dataset it occurs in. DQV provides the structure (metrics, dimensions and measurements), and each violation is a SHACL `sh:ValidationResult`:

```turtle
<urn:ontolint:measurement-6c1e61d32df4c31d> a dqv:QualityMeasurement ;
    dqv:isMeasurementOf <urn:ontolint:metric-properties-same-label> ;   # one dqv:Metric per check
    dqv:computedOn <https://example.org/ontology/activities#> ;  # the file's owl:Ontology IRI
    dqv:value 1 ;                                             # same count as the CTRF report
    olq:conforms false ;
    olq:severity sh:Violation ;
    olq:violation <urn:ontolint:violation-01a3e80ce17842a3>, <urn:ontolint:violation-82177d1ab5877598> .

<urn:ontolint:violation-01a3e80ce17842a3> a sh:ValidationResult ;
    sh:focusNode <https://example.org/ontology/activities#assignedTo> ;
    sh:value "assigned to"@en ;
    sh:resultMessage "shares label 'assigned to' with https://example.org/ontology/activities#delegatedTo" ;
    sh:resultSeverity sh:Violation ;
    sh:sourceConstraintComponent sh:SPARQLConstraintComponent ;
    olq:relatedResource <https://example.org/ontology/activities#delegatedTo> .
```

**See real reports:** [`tests/dqv/`](tests/dqv/) has end-to-end examples, each an input ontology next to the exact report ontolint produces for it (run with `--base-uri https://example.org/qa#`). The tests keep these files current.

| Example    | Input                                                                  | DQV report                                       | Shows                                                                                                              |
| ---------- | ---------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| clean      | [clean.ttl](tests/dqv/clean/clean.ttl)                                  | [expected.ttl](tests/dqv/clean/expected.ttl)      | A passing ontology: metric definitions and one conforming roll-up.                                                 |
| activities | [activities.ttl](tests/dqv/activities/activities.ttl)                   | [expected.ttl](tests/dqv/activities/expected.ttl) | Same-label clashes (shared label, related property, message) and an unresolvable import, each under its own check. |
| mixed      | [mixed.ttl](tests/dqv/mixed/mixed.ttl)                                  | [expected.ttl](tests/dqv/mixed/expected.ttl)      | Ten failing checks across all dimensions, at `sh:Violation` and `sh:Warning`.                                   |
| shapes     | [shapes.ttl](tests/dqv/shapes/shapes.ttl)                               | [expected.ttl](tests/dqv/shapes/expected.ttl)     | Anonymous SHACL property shapes, named by skolem IRIs.                                                             |
| per-file   | [a.ttl](tests/dqv/per-file/a.ttl), [b.ttl](tests/dqv/per-file/b.ttl)     | [expected.ttl](tests/dqv/per-file/expected.ttl)   | `--per-file`: one report, with each ontology's results computed on that ontology.                                |
| merged     | [one.ttl](tests/dqv/merged/one.ttl), [two.ttl](tests/dqv/merged/two.ttl) | [expected.ttl](tests/dqv/merged/expected.ttl)     | A merged run over two ontologies, computed on one aggregate `dcat:Dataset`.                                       |
| configuration | [configuration.ttl](tests/dqv/configuration/configuration.ttl) + [.rdf-lint.yml](tests/dqv/configuration/.rdf-lint.yml) | [expected.ttl](tests/dqv/configuration/expected.ttl) | The **effective configuration**: settings from the config file, ontolint defaults, bundled vocabularies and a rule, next to one failing measurement. The other examples leave the configuration out for readability. |

What gets emitted:

| Node | IRI | Notes |
|---|---|---|
| `dqv:Dimension` | `<base>dimension-<slug>` | `metadata`, `documentation`, `uniqueness`, `structure`, `conformance`. |
| `dqv:Metric` | `<base>metric-<slug>` | One per executed check, stable across runs, with `skos:prefLabel`, `rdfs:label`, `skos:definition`, `dqv:inDimension` and a default `olq:severity` (`sh:Violation` or `sh:Warning`). |
| `dqv:QualityMeasurement` | `<base>measurement-<hash>` | One per (dataset, failed check), with `dqv:value` (the check's count), `olq:conforms false`, `olq:severity` and one `olq:violation` per offending resource. Checks that pass have no measurement. |
| Roll-up `dqv:QualityMeasurement` | `<base>measurement-<hash>` | One per dataset for `<base>metric-ontolint-conformance`: `dqv:value` is the number of failed checks and `olq:conforms` is true only if all checks passed, so clean datasets still appear. |
| `sh:ValidationResult` | `<base>violation-<hash>` | `sh:focusNode` (the offending IRI), `sh:resultSeverity`, `sh:sourceConstraintComponent sh:SPARQLConstraintComponent` and, where applicable, `sh:value`, `sh:resultMessage` and `olq:relatedResource` (other resources involved, e.g. the other side of a same-label clash). |
| `dqv:QualityMetadata` | `<base>assessment-<hash>` | One per run, with `prov:generatedAtTime` and `dqv:hasQualityMeasurement` linking every measurement, and `olq:configuration` linking the configuration that ran. |
| `olq:Configuration` | `<base>configuration-<hash>` | The configuration the run actually used (see below). Identical configurations get the same IRI. |
| `olq:Setting` | `<base>setting-<hash>` | One setting of that configuration. |

- `olq:` is `https://ontolint.org/ns#`, defined in [`ontology/olq.ttl`](ontology/olq.ttl). It covers what DQV and SHACL don't. For results, that's `olq:conforms` and `olq:violation` on measurements (`sh:conforms` and `sh:result` have the domain `sh:ValidationReport`), `olq:severity` on metrics and measurements (`sh:severity` and `sh:resultSeverity` have the domains `sh:Shape` and `sh:AbstractResult`; its values are `sh:Severity` IRIs), and `olq:relatedResource` (SHACL has no equivalent). It also describes the effective configuration (`olq:Configuration`, `olq:Setting` and friends).
- **SHACL results:** violation nodes use the SHACL result vocabulary, so consumers can read them like a SHACL validation report. They omit `sh:sourceShape` (the checks are SPARQL queries, not shapes yet), so they are SHACL-shaped rather than strictly conforming results. The metric linked from the measurement identifies the check. Where a check can't name the offending resource (e.g. "some processed files have no `owl:Ontology`" in a merged run), the result has a message but no `sh:focusNode`.
- **Datasets:** `dqv:computedOn` is the `owl:Ontology` IRI declared in the checked graph, labelled from its `rdfs:label`, `dcterms:title` or `skos:prefLabel`. If there is no `owl:Ontology`, it falls back to the input file's `file:` IRI. Without `--per-file`, all inputs are one merged graph and a violation can't be traced to the ontology it came from. So when a merged run contains more than one ontology, its measurements are computed on a single aggregate `dcat:Dataset` (`<base>dataset-<hash>`, labelled `Merged: …`) that `dcterms:hasPart` each ontology, rather than being asserted on each of them. Use `--per-file` for per-ontology attribution; all files still go into one DQV report.
- **Blank nodes in the data:** results about blank nodes, such as anonymous SHACL property shapes, name them by a skolem IRI `<base>bnode-<hash>`. The hash is of the node's canonical label in the checked graph (rdflib's RGDA1 canonicalisation). Every blank node gets its own IRI, even structurally identical ones, and the IRI is the same for any parse of the same graph. Because the label depends on the whole graph, editing unrelated parts of the ontology can change it. Messages refer to such nodes as "a blank node". See the [shapes example](tests/dqv/shapes/expected.ttl).
- **IRIs:** no blank nodes are emitted. All instance IRIs are minted under `--base-uri` (default `urn:ontolint:`); if the base doesn't end in `/`, `#` or `:`, a `/` is added. Metrics and dimensions use their slug (`<base>metric-<slug>`, `<base>dimension-<slug>`), so the same check has the same IRI across runs with the same base. Measurements, violations and the assessment use a SHA-256 hash of the run timestamp, input files, dataset, metric and violation, so they're unique per run and reproducible for a given run. The `olq:` namespace holds only vocabulary terms (properties and classes), never instance data.
- No DQV report is written in `--profile-only` mode or when no file could be loaded.
- **Effective configuration:** the report records the configuration that actually ran, not just your `.rdf-lint.yml`. ontolint adds to and adjusts the file: default checks, the default `undefined-terms.skip-object-of` list, the [bundled vocabularies](#bundled-vocabularies) in `imports.local`, and rules such as re-enabling owl-declaration when a check that depends on it is selected. Each is an `olq:Setting` with:
  - `olq:key`: the `.rdf-lint.yml` key, e.g. `checks`, `imports.ignore`, `imports.local`, `exclude.types` or `undefined-terms.skip-object-of`;
  - `olq:value`: the check's metric, or the namespace, type or property;
  - `olq:origin`: `olq:ConfigFile`, `olq:OntolintDefault`, `olq:BundledVocabulary`, `olq:OntolintRule`, or `olq:CallerArgument` for values passed straight to `run_qa()` with no config file;
  - `rdfs:comment`: the reason;
  - `olq:enabled` for checks, `olq:localFile` for local imports, and `prov:wasDerivedFrom` linking a bundled vocabulary to its entry in the [vocabulary catalog](vocabularies/catalog.ttl).

  The configuration file's path is `olq:configurationFile`. For example:
  ```turtle
  <…#setting-…> a olq:Setting ;
      rdfs:label "checks: Ontology without declaration (enabled)" ;
      olq:key "checks" ;
      olq:value <…#metric-ontology-not-declared> ;
      olq:enabled true ;
      olq:origin olq:OntolintRule ;
      rdfs:comment "Enabled because the ontology-description check was selected and depends on it." .
  ```
- **Reproducible output:** set `SOURCE_DATE_EPOCH` (seconds since the Unix epoch) to pin the report timestamp. With the same inputs and base URI, the report, including every minted IRI, is then byte-for-byte reproducible.

## Dev setup & Running Ontolint locally

Install poetry with the [instructions here](https://python-poetry.org/docs/#installation), or `brew install poetry` if you're on mac with homebrew.

To test the script works, run the script using the example file:
``poetry run scripts/ontology_qa.py tests/example_pass.ttl``

It should generate a JSON files in the `ctrf/` directory.

To generate a markdown report, run the generate report script:
``poetry run scripts/generate_custom_report.py``

This generates a markdown file from any JSON files in the `ctrf/` directory and saves it to the `out/` directory

## New features

The backlog is managed in a [GitHub project](https://github.com/orgs/Semantic-partners/projects/3).

## Implementation

A collection of SPARQL queries to assess the quality of ontologies and executed with RDFLib. The script `ontology_qa.py` first creates a graph loading one or more ontologies. For quality assessment, one ontology at a time should be processed. The output is printed to the standard output in the markdown format.

`ontology_qa.py` Implements the following Profiling metrics:

| Metric Name                                   | Metric Description                                                                                                                                                      |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Number of triples                             | Axiom count                                                                                                                                                             |
| Class count                                   | Count number of `owl:Class` and `rdfs:Class`                                                                                                                         |
| Property count                                | Count number of `rdf:Property`,  `owl:ObjectProperty`, and `owl:DatatypeProperty`                                                                                  |
| NodeShape count                               | Count number of `sh:NodeShape`                                                                                                                                         |
| PropertyShape count                           | Count number of `sh:PropertyShape`                                                                                                                                     |
| Local classes constrained in NodeShapes       | Number of elements defined as both a (`rdfs:Class` or `owl:Class`) and `sh:NodeShape`, or a class defined in `sh:NodeShape` as the object of `sh:targetClass` |
| Local properties constrained in PropertyShape | Number of (`rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty`) defined in `sh:PropertyShapes` as the object of `sh:path`                         |
| Number of deprecated classes                  | Elements marked as `owl:DeprecatedClass`                                                                                                                               |
| Number of deprecated properties               | Elements marked as `owl:DeprecatedProperty`                                                                                                                            |
| Vocabularies used                             | Number of vocabularies used via a `@prefix` declaration                                                                                                                |
| Ontologies imported                           | Number of ontologies imported via `owl:imports`                                                                                                                        |
| Hierarchy depth                               | Number of levels from a root to a leaf class.                                                                                                                           |
| Average branching factor                      | Average number of subclasses per class.                                                                                                                                 |
| Cardinality restrictions                      | Number of `owl:Restriction` elements with `owl:cardinality`, `owl:minCardinality`, or `owl:maxCardinality` predicates.                                           |

And QA metrics:

| Metric Name                                   | Metric Description                                                                                                                                                                                                                                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Missing ontology declaration                  | No `owl:Ontology` tag declared                                                                                                                                                                                                                                                                  |
| Missing ontology description                  | `rdfs:comment`, `dcterms:abstract` or `dcterms:description` predicates not present                                                                                                                                                                                                         |
| Unresolvable imports                          | Verify that all `owl:imports` URLs resolve and contain triples                                                                                                                                                                                                                                  |
| Undefined terms                               | Find terms used in the ontology that are not defined locally (as a subject in the graph file) nor in their namespace's vocabulary (bundled, local, or fetched) |
| Classes missing label annotation              | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present (or any other local annotation property that is a subproperty of `rdfs:label`) |
| Properties missing label annotation           | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present (or any other local annotation property that is a subproperty of `rdfs:label`) |
| NodeShapes missing label annotation           | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present (or any other local annotation property that is a subproperty of `rdfs:label`) |
| PropertyShapes missing label annotation       | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present (or any other local annotation property that is a subproperty of `rdfs:label`) |
| Classes missing description annotation        | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present (or any other local annotation property that is a subproperty of `rdfs:comment`) |
| Properties missing description annotation     | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present (or any other local annotation property that is a subproperty of `rdfs:comment`) |
| NodeShapes missing description annotation     | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present (or any other local annotation property that is a subproperty of `rdfs:comment`) |
| PropertyShapes missing description annotation | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present (or any other local annotation property that is a subproperty of `rdfs:comment`) |
| Classes with the same label                   | Two or more entities have an identical label annotation in the same language tag and with the same predicate                                                                                                                                                                                     |
| Properties with the same label                | Same as above.                                                                                                                                                                                                                                                                                   |
| NodeShapes with the same label                | Same as above.                                                                                                                                                                                                                                                                                   |
| PropertyShapes with the same label            | Same as above.                                                                                                                                                                                                                                                                                   |
| Number of isolated classes                    | Classes declared but never used in any triple that connects them to the rest of the ontology.                                                                                                                                                                                                    |
| Property without domain                       | Property without rdfs:domain declaration.                                                                                                                                                                                                                                                        |
| Property without range                        | Property without rdfs:range declaration.                                                                                                                                                                                                                                                         |
| Non-unique identifiers                        | The same identifier is used to define multiple `owl:Class`, `rdfs:Class`, `rdf:Property`, `owl:ObjectProperty`, `owl:DatatypeProperty`, or `owl:AnnotationProperty`. The value refers to the total count.                                                                             |
| Subclass cycles                               | Classes involved in a `rdfs:subClassOf+` cycle.  The value refers to the total count.                                                                                                                                                                                                           |
| Untyped class                                 | An ontology element is used as a class without having been explicitly declared as such using the primitives `owl:Class` or `rdfs:Class`. The value refers to the actual number of untyped classes, as they do not appear in the total class count.                                            |
| Untyped property                              | An ontology element is used as a property without having been explicitly declared as such using the primitives `rdf:Property`, `owl:ObjectProperty` or `owl:DatatypeProperty`. The value refers to the actual number of untyped properties, as they do not appear in the total class count. |
| Namespace hijacking                           | Creating a class in the current namespace using the prefix of an external vocabulary. The script reports the count of subjects sorted by namespace. The user should then verify that the subjects are defined in the external ontology and not minted *ex-novo*.                                |

The Profiling and QA metrics are aggregated in two tables at the end of the markdown report. The QA metrics are normalised by the element count: for example a value of 0.5 for the metric *Class without label* means that half of all classes in the ontology do not have a label annotation. Note that a normalised value greater than 1 means that multiple violations of the same metric are present for at least some entities. For example, multiple classes having duplicate labels declared with the same predicate. An example of such tables for the test ontology [`example_failure.ttl`](tests/example_failure.ttl) follows:

### Profiling Metrics

| Name                   | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported | Hierarchy depth | Ave branching factor | Cardinality restrictions |
| ---------------------- | ----------------- | ----------- | -------------- | --------------- | ------------------- | -------------------------- | --------------------------------- | ---------------------- | ------------------------- | ----------------- | ------------------- | --------------- | -------------------- | ------------------------ |
| http://my.ont.example# | 68                | 11          | 5              | 3               | 1                   | 7                          | 1                                 | 1                      | 0                         | 6                 | 2                   | 0               | 3.500                | 0                        |

### Quality Assurance Metrics

| Name                   | Ontology not declared | Ontology without description | Unresolvable Imports | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
| ---------------------- | --------------------- | ---------------------------- | -------------------- | ------------------- | ---------------------- | ------------------------ | --------------------------- | ------------------------- | ---------------------------- | ------------------------------ | --------------------------------- | ----------------------- | -------------------------- | --------------------------- | ------------------------------- | ---------------- | ----------------------- | ---------------------- | ---------------------- | --------------- | --------------- | ------------------ | ------------------- |
| http://my.ont.example# | 0                     | 0                            | 1                    | 0.636               | 0.800                  | 0.667                    | 1                           | 0.909                     | 1                            | 1                              | 1                                 | 0.091                   | 0                          | 0                           | 0                               | 0.273            | 0                       | 0.400                  | 1                      | 0               | 3               | 0                  | 1                   |

### Batch Processing

For quality assessment, one ontology at a time should be processed. The following script runs `ontology_qa.py` and then uses `grep` to collect the output to two markdown tables.

```bash
#!/bin/bash

# Script path
sp=path/to/ontolint/scripts

# Run the QA metric script, save the results and grep the Profiling table.
for ont in *.ttl
do
 python3 $sp/ontology_qa.py $ont > ${ont%.ttl}.out
 grep -A 1 -e "|--|--|" ${ont%.ttl}.out | grep -v -e "--" | head -1 >> ont_tables.md
done

# Grep the QA metrics table.
echo "" >> ont_tables.md
for ont in *.ttl
do
 grep -A 1 -e "|--|--|" ${ont%.ttl}.out | grep -v -e "--" | tail -1 >> ont_tables.md
done
```

## GitHub Actions

Ontolint is published as a composite GitHub Action. No PAT or local setup is required — any repository in the Semantic Partners organisation can use it directly.

### Minimal setup

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

Replace `ontologies/` with the path to your ontology file or directory (relative to your repository root). That is all that is required.

A ready-to-use template is at [`templates/ci-example.yml`](templates/ci-example.yml).

### Checking multiple ontologies

`ontology-paths` accepts any number of files or directories — provide them one per line using YAML block scalar syntax (`|`):

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: |
      ontologies/core.ttl
      ontologies/shapes.ttl
      ontologies/extras/
```

All paths are loaded into a single combined graph before QA runs, so cross-ontology references resolve correctly.

To check each file on its own instead — one CTRF file and one report section per ontology — set `per-file: 'true'`:

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: ontologies/
    per-file: 'true'
```

In this mode each file is a separate graph, so references between files are not resolved.

When a directory is given, only files with a recognised RDF extension (`.ttl`, `.rdf`, `.owl`, `.xml`, `.nt`, `.n3`, `.jsonld`, `.trig`, …) are loaded; anything else (READMEs, configs) is skipped. Any file that is loaded but fails to parse — or an explicitly listed file that doesn't exist — fails the run with exit code 1, regardless of `fail-on-violations`. QA is not run against a partially loaded graph.

### Inputs

All inputs are strings (composite action convention). Pass booleans as `'true'` / `'false'`.

| Input                  | Default                 | Description                                                                                                                                                                                                                            |
| ---------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ontology-paths`     | —                      | **Required.** One or more paths to ontology files or directories, relative to the repository root.                                                                                                                               |
| `fail-on-violations` | `'true'`              | Exit with code 1 if any violations are found, causing the step to fail.                                                                                                                                                                |
| `verbose`            | `'false'`             | List every violating element under each failed check.                                                                                                                                                                                  |
| `profile-only`       | `'false'`             | Run profiling metrics only; skip all QA checks.                                                                                                                                                                                        |
| `per-file`           | `'false'`             | Run QA separately on each ontology file (directories expanded) rather than on one merged graph. Produces a CTRF file and report section per file (none when combined with `profile-only`; profiling is only printed to the step log). |
| `config-path`        | _(auto-detect)_       | Path to a lint configuration YAML file relative to the repository root. If omitted, the action looks for `.rdf-lint.yml` at the repository root and uses it when present.                                                             |
| `dqv`                | `'false'`             | Also write a[DQV](#dqv-report) Turtle report to `ctrf/<dqv-filename>`. It is included in the uploaded artifact and exposed as the `dqv-path` output.                                                                                |
| `dqv-filename`       | `'ontolint-dqv.ttl'`  | Filename of the DQV report.                                                                                                                                                                                                            |
| `base-uri`           | _(`urn:ontolint:`)_ | Namespace under which all DQV instance IRIs are minted: metrics, dimensions, measurements, violations and the assessment.                                                                                                              |
| `artifact-name`      | `'ontolint-ctrf'`     | Name of the uploaded CTRF artifact. Override when invoking the action in multiple jobs of the same run.                                                                                                                                |

### Outputs

| Output       | Description                                                                                                                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `dqv-path` | Absolute path of the DQV Turtle report, set only when`dqv: 'true'` and the report was written (not in `profile-only` mode, or if no RDF loaded). Use it to upload or publish the report in a later step: |

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

### What it produces

Each run writes a Markdown report to the Actions job summary (visible directly in the GitHub UI) and uploads a CTRF JSON artifact. Both are published whether the job passes or fails.

The one exception is `per-file: 'true'` combined with `profile-only: 'true'`: no QA checks run, so no CTRF files or report are produced. There is no job summary or artifact, and the profiling output appears only in the step log.

### Disabling individual checks

Place a `.rdf-lint.yml` file at your repository root:

```yaml
disable:
  - property-missing-domain
  - property-missing-range
```

The action picks it up automatically. To use a different location, pass `config-path`:

```yaml
- uses: Semantic-partners/ontolint@main
  with:
    ontology-paths: ontologies/
    config-path: config/ontolint.yml
```

### Excluding resources by type

Some encodings introduce resources that aren't real ontology terms. For example, when an RDF 1.2 ontology is downgraded to RDF 1.1, each triple term becomes an `rdf:PropositionForm` stand-in in the ontology's own namespace, and these would otherwise be flagged as untyped classes. List such types under `exclude.types` to skip their instances in the class checks (`class-missing-label`, `class-missing-comment`, `class-same-label`, `isolated-classes`, `untyped-class`). All other resources are still checked:

```yaml
exclude:
  types:
    - rdf:PropositionForm
```

Entries can be full IRIs or compact IRIs using the `rdf:`, `rdfs:`, `owl:`, `xsd:`, `skos:`, `sh:`, `dcterms:`, `foaf:`, `schema:` or `vs:` prefixes.

### Reference properties in the undefined-terms check

The undefined-terms check skips the objects of reference and documentation properties. Those objects are links to documents (a Wikipedia page, a licence), not ontology terms, so they are neither reported nor fetched. The same IRI used as a real term, as a subject or as the object of any other property, is still checked. The default properties are:

`rdfs:seeAlso`, `rdfs:isDefinedBy`, `dcterms:license`, `dcterms:source`, `dcterms:references`, `dcterms:relation`, `dcterms:conformsTo`, `owl:versionIRI`, `foaf:homepage`, `foaf:page`, `vs:*` (any [vocab-status](http://www.w3.org/2003/06/sw-vocab-status/ns#) property) and `schema:url` (both `https://` and `http://` schema.org).

To use your own list, set `undefined-terms.skip-object-of`. It **replaces** the defaults, `prefix:*` matches a whole namespace, and an empty list checks every object:

```yaml
undefined-terms:
  skip-object-of:
    - rdfs:seeAlso
    - dcterms:license
    - https://example.org/ns#docs
```

Entries use the same prefixes as `exclude.types`, plus `foaf:`, `schema:` and `vs:`. You don't need `imports.ignore` entries for `rdfs:seeAlso`, licence or source links; keep `imports.ignore` for importable namespaces you choose not to resolve.

### Bundled vocabularies

ontolint ships copies of the standard vocabularies in [`vocabularies/`](vocabularies/): RDF (with the RDF 1.2 terms), RDFS, OWL, XSD, SHACL, SKOS, Dublin Core (`dcterms`, `dc`, `dcam`, `dctype`), FOAF, VANN, Vocabulary Status, PROV, ORG, DCAT 3, vCard and schema.org (both `http://` and `https://`). They are used automatically, with no config:

- **Typos are caught, offline.** The undefined-terms check validates terms in these namespaces against the bundled files instead of trusting them. `skos:scopNote`, `dcterms:licence` and `xsd:strin` are reported. `skos:scopeNote`, `rdf:reifies`, `rdf:PropositionForm` and `xsd:dateTimeStamp` are not. Nothing is fetched for these namespaces, and `rdf:_1`, `rdf:_2`, … are always accepted.
- **`owl:imports` of these ontologies resolves locally,** e.g. `owl:imports <http://www.w3.org/2004/02/skos/core>`.

The run log shows which namespaces were resolved from the bundle (`bundled: skos.ttl`) and which were fetched. Sources, versions, licences and local edits are listed in [`vocabularies/README.md`](vocabularies/README.md).

**Behaviour change:** earlier versions trusted these namespaces without checking them, so a misspelt core term passed silently. It is now reported. To trust a namespace again, list it under `imports.ignore`.

The `imports` section of `.rdf-lint.yml` controls how namespaces and imports resolve:

```yaml
imports:
  # Trusted: never fetched, and its terms are never reported (undefined-terms);
  # owl:imports of it are not resolved (owl-imports).
  ignore:
    - http://example.org/vendor/ns#
  # Resolve a namespace / import from a local file instead of the network. An entry here
  # takes precedence over the bundled copy, e.g. to use a newer SHACL vocabulary.
  local:
    http://www.w3.org/ns/shacl#: vocab/shacl-1.2.ttl
    https://example.org/partner/ontology: vocab/partner.ttl
```

Entries match **with or without a trailing `#` or `/`**, so `http://www.w3.org/2004/02/skos/core` and `http://www.w3.org/2004/02/skos/core#` are the same entry. One entry covers both the namespace (used by undefined-terms) and the ontology IRI (used by owl-imports). Relative `local` paths are resolved from the config file's directory.

### Pinning to a version

For production use, pin to a specific release tag instead of `main`:

```yaml
- uses: Semantic-partners/ontolint@v1
```

## License

Licensed under either of

* Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
* MIT license ([LICENSE-MIT](LICENSE-MIT) or http://opensource.org/licenses/MIT)

at your option.
