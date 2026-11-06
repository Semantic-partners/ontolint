# Ontolint

Get an instant, user-friendly snapshot of your ontology’s size and health, right in your CI pipeline. This tool profiles your ontology file (triples, classes, properties, etc.) and runs quality checks (declarations, descriptions, versioning, structure), then produces a clear report so you can track complexity over time, catch regressions early, and keep your ontology consistently high-quality.

## What it's for

- **Gating changes in CI.** Run it on every pull request: a failing check fails the build,
  and the report lands in the job summary.
- **Catching what review misses.** Missing labels and descriptions, duplicate labels,
  typos in core-vocabulary terms (`skos:scopNote`), imports that don't resolve, subclass
  cycles, terms minted in someone else's namespace.
- **Tracking an ontology over time.** Profiling counts classes, properties, shapes,
  hierarchy depth and more, so growth and complexity are visible run to run.
- **Feeding other tools.** Results come as Markdown for people, CTRF JSON for CI
  dashboards and W3C DQV (RDF) for anything that reads RDF.

It reads Turtle, RDF/XML, OWL, N-Triples, JSON-LD and TriG, checks offline against bundled
copies of the core vocabularies, and only goes to the network for vocabularies it doesn't
have.

## What's in the repository

| Path | What it is |
|---|---|
| [`src/ontolint/`](https://github.com/Semantic-partners/ontolint/tree/main/src/ontolint) | The Python package: the checks, the `ontolint` command and the API |
| [`src/ontolint/sparql/`](https://github.com/Semantic-partners/ontolint/tree/main/src/ontolint/sparql) | The SPARQL queries behind the checks and metrics |
| [`src/ontolint/vocabularies/`](https://github.com/Semantic-partners/ontolint/tree/main/src/ontolint/vocabularies) | Bundled copies of the core vocabularies, for offline checking |
| [`action.yml`](https://github.com/Semantic-partners/ontolint/blob/main/action.yml) | The GitHub Action |
| [`ontology/olq.ttl`](https://github.com/Semantic-partners/ontolint/blob/main/ontology/olq.ttl) | The `olq:` vocabulary used in DQV reports |
| [`examples/`](https://github.com/Semantic-partners/ontolint/tree/main/examples) | A CI workflow to copy |
| [`docs/`](https://github.com/Semantic-partners/ontolint/tree/main/docs) | Reference for the action, the API, the configuration and the reports |
| [`tests/`](https://github.com/Semantic-partners/ontolint/tree/main/tests) | The test suite, including example ontologies and the reports they produce |

## Install

```bash
pip install ontolint
```

Ontolint needs Python 3.11 or later. Until the first PyPI release
([#94](https://github.com/Semantic-partners/ontolint/issues/94)), install it from GitHub:
`pip install git+https://github.com/Semantic-partners/ontolint`.

## Use it

### From the command line

```bash
ontolint my-ontology.ttl                  # report to stdout, CTRF JSON to ./ctrf/
ontolint ontologies/ -e                   # exit 1 if any check fails — for CI
ontolint ontologies/ --per-file           # check each file on its own
ontolint my-ontology.ttl -v               # also list every offending resource
ontolint my-ontology.ttl -p               # profiling only, no checks
ontolint my-ontology.ttl --dqv-dir out/   # also write the DQV (RDF) report
ontolint --init                           # write a starter .rdf-lint.yml
```

Given several files or a directory, ontolint checks them as one merged graph unless you pass
`--per-file`. `ontolint --help` lists every option. `ontolint-report --ctrf-dir ctrf`
combines CTRF files into one Markdown summary.

### In GitHub Actions

```yaml
jobs:
  ontolint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: Semantic-partners/ontolint@main
        with:
          ontology-paths: ontologies/
```

The action posts the report to the job summary and uploads the CTRF files. Inputs, outputs
and multi-ontology setups are in the
[action reference](https://github.com/Semantic-partners/ontolint/blob/main/docs/github-action.md).

### From Python

`lint()` checks graphs you already hold and returns the DQV report as a graph — no files,
no subprocess:

```python
import rdflib
from ontolint import Config, lint

report: rdflib.Graph = lint(
    [activities_graph, parties_graph],
    config=Config(per_file=True, imports=[schema_graph]),
)
```

`Config` and `lint` are the whole supported API. `Config` takes the same settings as the
config file:

| Field | Type | Default | `.rdf-lint.yml` / CLI equivalent |
|---|---|---|---|
| `per_file` | `bool` | `False` | `--per-file` |
| `imports` | `Iterable[Graph \| str \| PathLike]`, or a mapping of those by IRI | `{}` | `imports.local` — a vocabulary may be a graph as well as a path, and needs no key |
| `ignore_imports` | `Sequence[IRI]` | `()` | `imports.ignore` |
| `exclude_types` | `Sequence[IRI]` | `()` | `exclude.types` |
| `skip_object_of` | `Sequence[IRI] \| None` | `None` | `undefined-terms.skip-object-of` (`None` keeps the defaults) |
| `resolve_siblings` | `bool` | `True` | `imports.siblings` |
| `checks` | `Sequence[str] \| None` | `None` (all) | the `enable:` list |
| `base_iri` | `IRI \| None` | `urn:ontolint:` | `--base-uri` |
| `inference` | `bool` | `False` | `-i` / `--inference` |
| `uri_parser` | `Callable[[str], Graph] \| None` | fetch over the network | — pass a callable that raises to forbid network access |

Naming datasets, reading pass/fail from the report and the rest are in the
[API reference](https://github.com/Semantic-partners/ontolint/blob/main/docs/python-api.md).

## What it measures

### Profiling metrics

Counted on every run, reported but never failed:

| Metric | What it counts |
|---|---|
| Number of triples | Triples in the graph |
| Class count | `owl:Class` and `rdfs:Class` |
| Property count | `rdf:Property`, `owl:ObjectProperty` and `owl:DatatypeProperty` |
| NodeShape count | `sh:NodeShape` |
| PropertyShape count | `sh:PropertyShape` |
| Local classes in NodeShapes | Classes that are also a `sh:NodeShape`, or are the `sh:targetClass` of one |
| Local properties in PropertyShapes | Properties that are the `sh:path` of a `sh:PropertyShape` |
| Deprecated classes / properties | `owl:DeprecatedClass` and `owl:DeprecatedProperty` |
| Vocabularies used | Namespaces declared with a prefix |
| Ontologies imported | `owl:imports` |
| Hierarchy depth | Levels from a root class to a leaf |
| Average branching factor | Subclasses per class |
| Cardinality restrictions | `owl:Restriction`s with `owl:cardinality`, `owl:minCardinality` or `owl:maxCardinality` |

### Checks

Every check runs by default. Each is named as it appears in `.rdf-lint.yml`; the severity
is recorded in the DQV report, and with `-e` any failing check fails the run.

| Check | Fails when | Severity |
|---|---|---|
| `owl-declaration` | A processed file has no `owl:Ontology` declaration | Violation |
| `one-ontology-per-file` | One input declares more than one `owl:Ontology` | Violation |
| `owl-description` | The ontology has no `rdfs:comment`, `dcterms:abstract` or `dcterms:description` | Violation |
| `owl-imports` | An `owl:imports` target can't be resolved or is empty | Violation |
| `undefined-terms` | A term is defined neither locally nor in its vocabulary (bundled, local or fetched) | Violation |
| `class-missing-label` | A class has no label (`rdfs:label`, `skos:prefLabel`, … or a local subproperty of `rdfs:label`) | Violation |
| `property-missing-label` | A property has no label | Violation |
| `node-shape-missing-label` | A SHACL NodeShape has no label | Violation |
| `property-shape-missing-label` | A SHACL PropertyShape has no label | Violation |
| `class-missing-comment` | A class has no description (`rdfs:comment`, `dcterms:description`, `skos:definition`, … or a local subproperty of `rdfs:comment`) | Warning |
| `property-missing-comment` | A property has no description | Warning |
| `node-shape-missing-comment` | A SHACL NodeShape has no description | Warning |
| `property-shape-missing-comment` | A SHACL PropertyShape has no description | Warning |
| `class-same-label` | Two classes share a label in the same language, with the same predicate | Violation |
| `property-same-label` | Two properties share a label | Violation |
| `node-shape-same-label` | Two SHACL NodeShapes share a label | Violation |
| `property-shape-same-label` | Two SHACL PropertyShapes share a label | Violation |
| `isolated-classes` | A class is declared but not connected to the rest of the ontology | Warning |
| `property-missing-domain` | A property has no `rdfs:domain` | Warning |
| `property-missing-range` | A property has no `rdfs:range` | Warning |
| `unique-identifiers` | One IRI is declared as more than one kind of class or property | Violation |
| `subclass-cycles` | A class is part of an `rdfs:subClassOf` cycle | Violation |
| `untyped-class` | A term in the ontology's namespace is used as a class but not declared as one | Violation |
| `untyped-property` | A term in the ontology's namespace is used as a property but not declared as one | Violation |
| `hijacking` | A resource is defined in an external vocabulary's namespace | Violation |

Across the inputs of one run, ontolint also reports `duplicate-ontology-iri` when two
inputs declare the same `owl:Ontology` IRI.

## Configure it

Put a `.rdf-lint.yml` in the directory you run from (or pass `-c path`). Every key is
optional:

```yaml
disable:                        # or `enable:` to run only the checks listed
  - property-missing-domain
  - property-missing-range

exclude:
  types:                        # skip instances of these types in the class checks
    - rdf:PropositionForm

undefined-terms:
  skip-object-of:               # replaces the default list of reference properties
    - rdfs:seeAlso

imports:
  ignore:                       # trusted: never fetched or reported
    - http://example.org/vendor/ns#
  local:                        # resolve a namespace or import from a file
    https://example.org/partner/ontology: vocab/partner.ttl
  siblings: true                # resolve against the other inputs of the run (default)
```

Core vocabularies (RDF, RDFS, OWL, XSD, SHACL, SKOS, Dublin Core, FOAF, PROV, DCAT,
schema.org and more) are bundled, so terms in them are checked offline with no
configuration. Every setting, with its defaults, is in the
[configuration reference](https://github.com/Semantic-partners/ontolint/blob/main/docs/configuration.md).

## Reports

Each run's results come out as Markdown for a reader, CTRF JSON for CI tooling and,
optionally, W3C DQV Turtle with one node per violation. The formats, and worked DQV
examples, are in the
[reports reference](https://github.com/Semantic-partners/ontolint/blob/main/docs/reports.md).

## Contributing

See [DEVELOPING.md](https://github.com/Semantic-partners/ontolint/blob/main/DEVELOPING.md)
for setup, the code layout and the tests, and
[design.md](https://github.com/Semantic-partners/ontolint/blob/main/design.md) for how a run
is put together. The backlog is a
[GitHub project](https://github.com/orgs/Semantic-partners/projects/3).

## License

Licensed under either of

* Apache License, Version 2.0 ([LICENSE-APACHE](https://github.com/Semantic-partners/ontolint/blob/main/LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
* MIT license ([LICENSE-MIT](https://github.com/Semantic-partners/ontolint/blob/main/LICENSE-MIT) or http://opensource.org/licenses/MIT)

at your option.
