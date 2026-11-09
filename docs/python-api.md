# The Ontolint Python API

If your ontologies are already in memory — fetched from object storage, generated at
runtime, or transformed before linting — you don't have to go through files and a
subprocess. Hand `lint()` the graphs as they are — a graph that declares its own
`owl:Ontology` needs no name, and a vocabulary needs no key — and it returns the DQV
report as a graph.

**The package exports exactly two names, `Config` and `lint`** — that is the whole
supported surface, and a test pins it. `help(ontolint.Config)` lists every setting; the
table below is the same list.

```python
import rdflib
from ontolint import Config, lint

report: rdflib.Graph = lint(
    [activities_graph, parties_graph],
    config=Config(
        per_file=True,
        # dependency vocabularies as graphs, not paths: nothing is fetched or read from disk
        imports=[schema_graph],
        exclude_types=["rdf:PropositionForm"],
        base_iri="https://example.org/reports/run-123-/",
    ),
)

DQV = rdflib.Namespace("http://www.w3.org/ns/dqv#")
for measurement in report.subjects(rdflib.RDF.type, DQV.QualityMeasurement):
    ...
```

No temporary directory, no `.rdf-lint.yml`, no subprocess, no output file to read back.
The graphs you pass are never modified: each is copied before the checks run.

## Naming datasets

**You only need to name a graph that doesn't declare its own `owl:Ontology`.** A declared
ontology IRI is what the dataset is reported under in any case, so pulling it out yourself
only repeats what ontolint already reads. Pass one graph, a list of them, or a mapping:

```python
lint(graph)                                        # one
lint([activities_graph, parties_graph])            # several
lint({"https://example.org/parties": parties})     # named
```

**One file, one ontology.** If two inputs declare the same `owl:Ontology` IRI, that is
reported as a `duplicate-ontology-iri` finding naming both of them, and every other check
still runs — the run is not refused. The condition is detected before the inputs are
merged, since merging two identical declarations leaves a single triple. The CLI reports
it the same way, in both `--per-file` and grouped runs.

An unnamed graph that declares no ontology falls back to `unnamed-1`, `unnamed-2` by
position — stable for the same order and no more, so name those if you want to compare
runs. A name that is itself an absolute IRI identifies the dataset as it stands, so runs
on different machines line up in a shared graph; any other name (`"activities"`) is a
local label, minted under `base_iri` as `…dataset-activities`.

`per_file=True` checks each dataset on its own, so every violation is attributed to the
dataset it came from; the default merges them into one graph, as the CLI does when given
several files without `--per-file`.

## Config

`Config` is the single description of a lint run — the CLI builds one from its arguments
and `.rdf-lint.yml`, and you build one directly.

| Field | Type | Default | [`.rdf-lint.yml`](configuration.md) / CLI equivalent |
|---|---|---|---|
| `per_file` | `bool` | `False` | `--per-file` |
| `imports` | `Iterable[Graph \| str \| PathLike]`, or a mapping of those by IRI | `{}` | `imports.local` — a vocabulary may be a graph as well as a path, and needs no key |
| `ignore_imports` | `Sequence[IRI]` | `()` | `imports.ignore` |
| `exclude_types` | `Sequence[IRI]` | `()` | `exclude.types` (a CURIE is a `str`, so the type is a union) |
| `skip_object_of` | `Sequence[IRI] \| None` | `None` | `undefined-terms.skip-object-of` (`None` keeps the defaults) |
| `resolve_siblings` | `bool` | `True` | `imports.siblings` — with `per_file`, each dataset resolves against the others of the same call |
| `checks` | `Sequence[str] \| None` | `None` (all) | the `enable:` list, named the same way |
| `base_iri` | `IRI \| None` | `urn:ontolint:` | `--base-uri` |
| `inference` | `bool` | `False` | `-i` / `--inference` |
| `uri_parser` | `Callable[[str], Graph] \| None` | fetch over the network | — pass a callable that raises to forbid network access |

### Keying `imports`

**Keys are optional here too.** Pass a plain list of vocabularies and each is registered
under everything it defines — its `owl:Ontology` IRI and the namespace of every term in
it — which is less work than naming them and more accurate than picking one main namespace
for a vocabulary that spans several:

```python
Config(imports=[schema_graph, owl_graph])          # unkeyed
Config(imports={"https://schema.org/": schema_graph})   # or keyed, if you prefer
```

If you do key them, the form doesn't matter: keys are matched ignoring one trailing `#` or
`/`, so `.../core`, `.../core#` and `.../core/` are the same entry — which is why a hash
vocabulary whose ontology IRI omits the `#` (as OWL's own does) still resolves. Terms are
looked up across every vocabulary you supply, so one entry covers all the namespaces that
graph defines.

`IRI` is `str | rdflib.URIRef`: pass `URIRef`s where you have them, and the union still
admits the CURIEs (`rdf:PropositionForm`) and `<namespace>*` wildcards that two of these
fields accept, which are strings but not IRIs. Dataset names are typed the same way.

Naming a check that doesn't exist raises `ValueError` rather than silently running
nothing. The dependencies between checks are the CLI's: asking for `owl-description`
pulls in `owl-declaration`, which it needs, and `undefined-terms` needs it too in order
to tell a local namespace from one it has to resolve.

## Pass or fail

The report carries an `ontolint-conformance` measurement per dataset: `olq:conforms` says
whether every executed check passed, and `dqv:value` counts those that didn't. That is how
you get an exit code out of it:

```python
DQV = rdflib.Namespace("http://www.w3.org/ns/dqv#")
OLQ = rdflib.Namespace("https://ontolint.org/ns#")
rollup = rdflib.URIRef("urn:ontolint:metric-ontolint-conformance")   # or <base_iri>metric-…

failed = {
    str(report.value(m, DQV.computedOn))
    for m in report.subjects(DQV.isMeasurementOf, rollup)
    if not report.value(m, OLQ.conforms).toPython()
}
```

## One run, two front ends

`lint()` is not a parallel implementation of the CLI. Both build a `Config`, and both hand
it to `ontolint.runner.lint_graph()` — inference, check selection and every check happen in
exactly one place. The CLI adds file loading, Markdown, CTRF and exit codes on top; the API
adds graph copying and dataset naming. Neither has its own copy of what a lint run means.

The modules behind it (`ontolint.runner`, `ontolint.checks`, …) are importable, but they are
internal and may change in any release: only `Config` and `lint` are supported.
