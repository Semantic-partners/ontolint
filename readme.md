# Ontolint: Ontology Quality Assessment

Get an instant, user-friendly snapshot of your ontology’s size and health, right in your CI pipeline. This tool profiles your ontology file (triples, classes, properties, etc.) and runs quality checks (declarations, descriptions, versioning, structure), then produces a clear report so you can track complexity over time, catch regressions early, and keep your ontology consistently high-quality.

## Usage

We have a [Github workflow](/.github/workflows/validate-ontolint.yml) running against two [example ontologies](./tests/) - use this as a reference.

The [`ontology_qa.py`](./scripts/ontology_qa.py) script performs quality assurance on a set of ontologies. It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to check for common ontology quality issues. It reports any violations found in the ontology data.

```
usage: ontology_qa.py [-h] [-e] [-v] [-p] [-i] [--ctrf-dir directory] [--ctrf-filename filename] [-o filename] [-c path/to/config.yml] [--init] [data_files ...]

A script to perform basic QA on a set of ontologies. It loads RDF files, applies simple RDFS subclass inference, and
runs SPARQL queries to check for common ontology quality issues. It reports any violations found in the ontology data.

positional arguments:
  data_files            List of RDF files or folders to process.

options:
  -h, --help            Show this help message and exit.
  -e, --exit-status     Report an exit status to determine if one or more violations were detected.
  -v, --verbose         Enable verbose output.
  -p, --profile-only    Compute only the profiling metrics and skip the QA part.
  -i, --inference       Enable inference of subclass relations before running QA checks.(default: False)
  --ctrf-dir directory  Directory to write CTRF report to.
  --ctrf-filename filename
                        Filename for CTRF report (if None, uses default pattern).
  -o filename, --output filename
                        Output file name (optional). If omitted, print to stdout.
  -c path/to/config.yml, --config path/to/config.yml
                        Path to a YAML configuration file to enable or disable individual checks. Note that if
                        the current directory contains a .rdf-lint.yml file, it will be used by default.
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

## Dev setup & Running Ontolint locally
Install poetry with the [instructions here](https://python-poetry.org/docs/#installation), or `brew install poetry` if you're on mac with homebrew.

To test the script works, run the script using the example file:
```poetry run scripts/ontology_qa.py tests/example_pass.ttl```

It should generate a JSON files in the `ctrf/` directory.

To generate a markdown report, run the generate report script:
```poetry run scripts/generate_custom_report.py```

This generates a markdown file from any JSON files in the `ctrf/` directory and saves it to the `out/` directory

## New features

The backlog is managed in a [GitHub project](https://github.com/orgs/Semantic-partners/projects/3).

## Implementation

A collection of SPARQL queries to assess the quality of ontologies and executed with RDFLib. The script `ontology_qa.py` first creates a graph loading one or more ontologies. For quality assessment, one ontology at a time should be processed. The output is printed to the standard output in the markdown format.

`ontology_qa.py` Implements the following Profiling metrics:

| Metric Name                                   | Metric Description                                           |
| --------------------------------------------- | ------------------------------------------------------------ |
| Number of triples                             | Axiom count                                                  |
| Class count                                   | Count number of `owl:Class` and `rdfs:Class`                 |
| Property count                                | Count number of `rdf:Property`,  `owl:ObjectProperty`, and `owl:DatatypeProperty` |
| NodeShape count                               | Count number of `sh:NodeShape`                               |
| PropertyShape count                           | Count number of `sh:PropertyShape`                           |
| Local classes constrained in NodeShapes       | Number of elements defined as both a (`rdfs:Class` or `owl:Class`) and `sh:NodeShape`, or a class defined in `sh:NodeShape` as the object of `sh:targetClass` |
| Local properties constrained in PropertyShape | Number of (`rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty`) defined in `sh:PropertyShapes` as the object of `sh:path` |
| Number of deprecated classes                  | Elements marked as `owl:DeprecatedClass`                     |
| Number of deprecated properties               | Elements marked as `owl:DeprecatedProperty`                  |
| Vocabularies used                             | Number of vocabularies used via a `@prefix` declaration      |
| Ontologies imported                           | Number of ontologies imported via `owl:imports`              |
| Hierarchy depth                               | Number of levels from a root to a leaf class.                |
| Average branching factor                      | Average number of subclasses per class.                      |
| Cardinality restrictions                      | Number of `owl:Restriction` elements with `owl:cardinality`, `owl:minCardinality`, or `owl:maxCardinality` predicates. |

And QA metrics:

| Metric Name                                   | Metric Description                                           |
| --------------------------------------------- | ------------------------------------------------------------ |
| Missing ontology declaration                  | No `owl:Ontology` tag declared                               |
| Missing ontology description                  | `rdfs:comment`, `dcterms:abstract` or `dcterms:description` predicates not present |
| Unresolvable imports                          | Verify that all `owl:imports` URLs resolve and contain triples |
| Undefined terms                               | Find terms used in the ontology that are not defined locally (as a subject in the graph file) nor in any successfully-fetched remote ontology |
| Classes missing label annotation              | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present |
| Properties missing label annotation           | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present |
| NodeShapes missing label annotation           | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present |
| PropertyShapes missing label annotation       | `rdfs:label`,  `skos:prefLabel`, `skos:altLabel`, or `skos:hiddenLabel` predicates not present |
| Classes missing description annotation        | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present |
| Properties missing description annotation     | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present |
| NodeShapes missing description annotation     | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present |
| PropertyShapes missing description annotation | `rdfs:comment`, `dcterms:description`, or `skos:definition` predicates not present |
| Classes with the same label                   | Two or more entities have an identical label annotation in the same language tag |
| Properties with the same label                | Same as above.                                               |
| NodeShapes with the same label                | Same as above.                                               |
| PropertyShapes with the same label            | Same as above.                                               |
| Number of isolated classes                    | Classes declared but never used in any triple that connects them to the rest of the ontology. |
| Property without domain                       | Property without rdfs:domain declaration.                    |
| Property without range                        | Property without rdfs:range declaration.                     |
| Non-unique identifiers                        | The same identifier is used to define multiple `owl:Class`, `rdfs:Class`, `rdf:Property`, `owl:ObjectProperty`, `owl:DatatypeProperty`, or `owl:AnnotationProperty`. The value refers to the total count. |
| Subclass cycles                               | Classes involved in a `rdfs:subClassOf+` cycle.  The value refers to the total count. |
| Untyped class                                 | An ontology element is used as a class without having been explicitly declared as such using the primitives `owl:Class` or `rdfs:Class`. The value refers to the actual number of untyped classes, as they do not appear in the total class count. |
| Untyped property                              | An ontology element is used as a property without having been explicitly declared as such using the primitives `rdf:Property`, `owl:ObjectProperty` or `owl:DatatypeProperty`. The value refers to the actual number of untyped properties, as they do not appear in the total class count. |
| Namespace hijacking                           | Creating a class in the current namespace using the prefix of an external vocabulary. The script reports the count of subjects sorted by namespace. The user should then verify that the subjects are defined in the external ontology and not minted *ex-novo*. |

For example, the test ontology [`example_failure.ttl`](tests/example_failure.ttl) returns the following results:

### Profiling Metrics

| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported | Hierarchy depth | Ave branching factor | Cardinality restrictions |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| http://my.ont.example# | 68 | 11 | 5 | 3 | 1 | 7 | 1 | 1 | 0 | 6 | 2 | 0 | 3.500 | 0 |

### Quality Assurance Metrics

| Name | Ontology not declared | Ontology without description | Unresolvable Imports | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| http://my.ont.example# | 0 | 0 | 1 | 0.636 | 0.800 | 0.667 | 1 | 0.909 | 1 | 1 | 1 | 0.091 | 0 | 0 | 0 | 0.273 | 0 | 0.400 | 1 | 0 | 3 | 0 | 1 |

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

### Inputs

All inputs are strings (composite action convention). Pass booleans as `'true'` / `'false'`.

| Input | Default | Description |
|---|---|---|
| `ontology-paths` | — | **Required.** One or more paths to ontology files or directories, relative to the repository root. |
| `fail-on-violations` | `'true'` | Exit with code 1 if any violations are found, causing the step to fail. |
| `verbose` | `'false'` | List every violating element under each failed check. |
| `profile-only` | `'false'` | Run profiling metrics only; skip all QA checks. |
| `config-path` | _(auto-detect)_ | Path to a lint configuration YAML file relative to the repository root. If omitted, the action looks for `.rdf-lint.yml` at the repository root and uses it when present. |
| `artifact-name` | `'ontolint-ctrf'` | Name of the uploaded CTRF artifact. Override when invoking the action in multiple jobs of the same run. |

### What it produces

Each run writes a Markdown report to the Actions job summary (visible directly in the GitHub UI) and uploads a CTRF JSON artifact. Both are published whether the job passes or fails.

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

### Pinning to a version

For production use, pin to a specific release tag instead of `main`:

```yaml
- uses: Semantic-partners/ontolint@v1
```
