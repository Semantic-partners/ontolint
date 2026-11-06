# Ontolint reports

A run produces up to three reports of the same results, each for a different reader:

| Report | For | Written |
|---|---|---|
| [Markdown](#markdown) | a person | to stdout, or to `-o FILE` |
| [CTRF](#ctrf) JSON | CI dashboards and test reporters | on every run that checks (not `-p`), to `--ctrf-dir` (default `ctrf/`) |
| [DQV](#dqv) Turtle | anything that reads RDF | when `--dqv-dir` or `--dqv-filename` is given |

None of them runs a check: each is a projection of the same result, so they always agree.

## Markdown

The report lists the profiling details, then each check with its outcome — and, with `-v`,
every offending resource — and ends with two summary tables, one row per ontology: the
profiling metrics, and the QA metrics.

The QA metrics are normalised by the element count: a value of 0.5 for *Class without
label* means half of the ontology's classes have no label. A value above 1 means some
entities violate the same check more than once — several classes sharing a label under the
same predicate, for example. A check that was not selected reads `N/A`; one that could not be
computed is marked as skipped. For [`tests/example_failure.ttl`](../tests/example_failure.ttl):

```
## Profiling Metrics
| Name | Number of triples | Class count | Property count | NodeShape count | ...
|--|--|--|--|--| ...
| http://my.ont.example# | 70 | 11 | 5 | 3 | ...
```

## CTRF

[CTRF](https://ctrf.io) is a common JSON format for test results, so CI tooling that
understands test reports can show ontolint's: one test per check, `passed`, `failed` or
`skipped`, with the violation count and offending elements. `--per-file` writes one file per
input, named after it.

`ontolint-report` combines every CTRF file in a directory into one Markdown summary — what
the GitHub Action posts as the job summary:

```bash
ontolint-report --ctrf-dir ctrf --output-path out/ctrf_report.md
```

`--template-path` renders it with your own Handlebars template instead of the bundled one.

## DQV

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

**See real reports:** [`tests/dqv/`](../tests/dqv/) has end-to-end examples, each an input ontology next to the exact report ontolint produces for it (run with `--base-uri https://example.org/qa#`). The tests keep these files current.

| Example    | Input                                                                  | DQV report                                       | Shows                                                                                                              |
| ---------- | ---------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| clean      | [clean.ttl](../tests/dqv/clean/clean.ttl)                                  | [expected.ttl](../tests/dqv/clean/expected.ttl)      | A passing ontology: metric definitions and one conforming roll-up.                                                 |
| activities | [activities.ttl](../tests/dqv/activities/activities.ttl)                   | [expected.ttl](../tests/dqv/activities/expected.ttl) | Same-label clashes (shared label, related property, message) and an unresolvable import, each under its own check. |
| mixed      | [mixed.ttl](../tests/dqv/mixed/mixed.ttl)                                  | [expected.ttl](../tests/dqv/mixed/expected.ttl)      | Ten failing checks across all dimensions, at `sh:Violation` and `sh:Warning`.                                   |
| shapes     | [shapes.ttl](../tests/dqv/shapes/shapes.ttl)                               | [expected.ttl](../tests/dqv/shapes/expected.ttl)     | Anonymous SHACL property shapes, named by skolem IRIs.                                                             |
| per-file   | [a.ttl](../tests/dqv/per-file/a.ttl), [b.ttl](../tests/dqv/per-file/b.ttl)     | [expected.ttl](../tests/dqv/per-file/expected.ttl)   | `--per-file`: one report, with each ontology's results computed on that ontology.                                |
| merged     | [one.ttl](../tests/dqv/merged/one.ttl), [two.ttl](../tests/dqv/merged/two.ttl) | [expected.ttl](../tests/dqv/merged/expected.ttl)     | A merged run over two ontologies, computed on one aggregate `dcat:Dataset`.                                       |
| configuration | [configuration.ttl](../tests/dqv/configuration/configuration.ttl) + [.rdf-lint.yml](../tests/dqv/configuration/.rdf-lint.yml) | [expected.ttl](../tests/dqv/configuration/expected.ttl) | The **effective configuration**: settings from the config file, ontolint defaults, bundled vocabularies and a rule, next to one failing measurement. The other examples leave the configuration out for readability. |

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

- `olq:` is `https://ontolint.org/ns#`, defined in [`ontology/olq.ttl`](../ontology/olq.ttl). It covers what DQV and SHACL don't. For results, that's `olq:conforms` and `olq:violation` on measurements (`sh:conforms` and `sh:result` have the domain `sh:ValidationReport`), `olq:severity` on metrics and measurements (`sh:severity` and `sh:resultSeverity` have the domains `sh:Shape` and `sh:AbstractResult`; its values are `sh:Severity` IRIs), and `olq:relatedResource` (SHACL has no equivalent). It also describes the effective configuration (`olq:Configuration`, `olq:Setting` and friends).
- **SHACL results:** violation nodes use the SHACL result vocabulary, so consumers can read them like a SHACL validation report. They omit `sh:sourceShape` (the checks are SPARQL queries, not shapes yet), so they are SHACL-shaped rather than strictly conforming results. The metric linked from the measurement identifies the check. Where a check can't name the offending resource (e.g. "some processed files have no `owl:Ontology`" in a merged run), the result has a message but no `sh:focusNode`.
- **Datasets:** `dqv:computedOn` is the `owl:Ontology` IRI declared in the checked graph, labelled from its `rdfs:label`, `dcterms:title` or `skos:prefLabel`. If there is no `owl:Ontology`, it falls back to the input file's `file:` IRI. Without `--per-file`, all inputs are one merged graph and a violation can't be traced to the ontology it came from. So when a merged run contains more than one ontology, its measurements are computed on a single aggregate `dcat:Dataset` (`<base>dataset-<hash>`, labelled `Merged: …`) that `dcterms:hasPart` each ontology, rather than being asserted on each of them. Use `--per-file` for per-ontology attribution; all files still go into one DQV report.
- **Blank nodes in the data:** results about blank nodes, such as anonymous SHACL property shapes, name them by a skolem IRI `<base>bnode-<hash>`. The hash is of the node's canonical label in the checked graph (rdflib's RGDA1 canonicalisation). Every blank node gets its own IRI, even structurally identical ones, and the IRI is the same for any parse of the same graph. Because the label depends on the whole graph, editing unrelated parts of the ontology can change it. Messages refer to such nodes as "a blank node". See the [shapes example](../tests/dqv/shapes/expected.ttl).
- **IRIs:** no blank nodes are emitted. All instance IRIs are minted under `--base-uri` (default `urn:ontolint:`); if the base doesn't end in `/`, `#` or `:`, a `/` is added. Metrics and dimensions use their slug (`<base>metric-<slug>`, `<base>dimension-<slug>`), so the same check has the same IRI across runs with the same base. Measurements, violations and the assessment use a SHA-256 hash of the run timestamp, input files, dataset, metric and violation, so they're unique per run and reproducible for a given run. The `olq:` namespace holds only vocabulary terms (properties and classes), never instance data.
- No DQV report is written in `--profile-only` mode or when no file could be loaded.
- **Effective configuration:** the report records the configuration that actually ran, not just your `.rdf-lint.yml`. ontolint adds to and adjusts the file: default checks, the default `undefined-terms.skip-object-of` list, the [bundled vocabularies](configuration.md#bundled-vocabularies) in `imports.local`, and rules such as re-enabling owl-declaration when a check that depends on it is selected. Each is an `olq:Setting` with:
  - `olq:key`: the `.rdf-lint.yml` key, e.g. `checks`, `imports.ignore`, `imports.local`, `exclude.types` or `undefined-terms.skip-object-of`;
  - `olq:value`: the check's metric, or the namespace, type or property;
  - `olq:origin`: `olq:ConfigFile`, `olq:OntolintDefault`, `olq:BundledVocabulary`, `olq:OntolintRule`, or `olq:CallerArgument` for values passed straight to `run_qa()` with no config file;
  - `rdfs:comment`: the reason;
  - `olq:enabled` for checks, `olq:localFile` for local imports, and `prov:wasDerivedFrom` linking a bundled vocabulary to its entry in the [vocabulary catalog](../src/ontolint/vocabularies/catalog.ttl).

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
- **Reproducible output:** every minted IRI derives from the report timestamp, so a CLI run carries the wall clock. Pin it — `dqv.build_dqv_graph(results, date_time_provider=…)` — and the report, including every minted IRI, is byte-for-byte reproducible for the same inputs and base URI.
