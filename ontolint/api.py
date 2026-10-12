"""
Ontolint's programmatic entry point: lint graphs you already hold, get a graph back.

The checks have always worked on an `rdflib.Graph`; this module exposes that layer
without the command line, so a caller whose ontologies are already in memory doesn't
have to serialise them to a temporary directory and read a report file back.

    import rdflib
    from ontolint import Config, lint

    report = lint(
        {"https://example.org/activities": activities_graph,
         "https://example.org/parties": parties_graph},
        config=Config(per_file=True, imports={"https://schema.org/": schema_graph}),
    )

`report` is a DQV graph: the same one the CLI writes with --dqv-dir.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import rdflib

from scripts import dqv
from scripts import ontology_qa as qa
from scripts.ontology_qa import CheckResult, QAResult

__all__ = ["Config", "lint", "lint_results", "CheckResult", "QAResult"]


@dataclass
class Config:
    """
    How a `lint()` run is configured — the programmatic form of `.rdf-lint.yml`.

    per_file:       check each dataset on its own, so every violation is attributed to the
                    dataset it came from. The default merges them into one graph, which is
                    what you want when they only make sense together (the equivalent of
                    passing several files to the CLI without --per-file).
    imports:        namespace or import IRI -> the vocabulary that defines it, as an
                    `rdflib.Graph` or a path to a file. The in-memory equivalent of
                    `imports.local`, so references resolve with no network access. The
                    vocabularies bundled with ontolint are merged in underneath, and an
                    entry here overrides a bundled one for the same namespace.
    ignore_imports: namespaces and import IRIs that are trusted: never fetched, never
                    reported, never resolved (`imports.ignore`).
    exclude_types:  type IRIs, or CURIEs in ontolint's config prefixes (e.g.
                    "rdf:PropositionForm"), whose instances the class checks skip
                    (`exclude.types`).
    skip_object_of: predicate IRIs or `<namespace>*` wildcards whose objects the
                    undefined-terms check treats as links to documents rather than terms
                    (`undefined-terms.skip-object-of`). None keeps ontolint's defaults; an
                    empty sequence skips nothing.
    checks:         the checks to run, named as in `.rdf-lint.yml` (e.g.
                    "class-missing-label"). None, the default, runs all of them. Naming a
                    check that doesn't exist is an error rather than a silent no-op.
    base_iri:       the namespace the DQV report mints its IRIs under. Give each run its
                    own (e.g. ".../run-123-") when reports are collected into one graph.
    inference:      apply RDFS subclass inference before checking, as the CLI's -i does.
    uri_parser:     how a namespace outside `imports` is fetched by the undefined-terms
                    check; the default parses the namespace IRI over the network. Pass a
                    callable that raises to forbid network access entirely.
    """

    per_file: bool = False
    imports: Mapping[str, "rdflib.Graph | str"] = field(default_factory=dict)
    ignore_imports: Sequence[str] = ()
    exclude_types: Sequence[str] = ()
    skip_object_of: Sequence[str] | None = None
    checks: Sequence[str] | None = None
    base_iri: str | None = None
    inference: bool = False
    uri_parser: Callable[[str], rdflib.Graph] | None = None


def lint(datasets: Mapping[str, "rdflib.Graph | str"], config: Config | None = None) -> rdflib.Graph:
    """
    Check the given graphs and return the results as a DQV graph.

    datasets maps a name you choose to the graph to check. **Prefer the ontology's IRI as
    the name**: a name that is already an absolute IRI is used as the dataset's identity in
    the report as it stands, so the same dataset is identified the same way across runs,
    machines and callers, and reports collected into one graph line up. Any other name is
    a local label, minted into an IRI under `base_iri` and meaningful only within these
    reports. Either way, a graph that declares its own `owl:Ontology` is reported under
    that IRI, and the name is only how you referred to it.

    A value may also be a Turtle string, which is parsed for you.

    The returned graph is the one the CLI writes with --dqv-dir: `dqv:QualityMeasurement`s
    of each failed check, `sh:ValidationResult`s naming the offending resources, and the
    configuration the run used. Serialise it, add it to a store, or query it directly.

    The graphs you pass are never modified: each is copied before inference runs and before
    the checks exclude instance data from it.
    """
    return dqv.build_dqv_graph(lint_results(datasets, config), base_uri=(config or Config()).base_iri)


def lint_results(datasets: Mapping[str, "rdflib.Graph | str"], config: Config | None = None) -> list[QAResult]:
    """
    The structured results behind `lint()`: one QAResult per dataset, or one for the merged
    run. Use it when you want the pass/fail of each check directly — `result.passed`,
    `result.failures`, `result.get("Class without label")` — rather than querying the graph.
    """
    config = config or Config()
    graphs = _prepare(datasets)
    _check_base_iri(config.base_iri)
    checklist, lint_config, rule_reasons = _select_checks(config.checks)
    kwargs = _run_kwargs(config, checklist, lint_config, rule_reasons)

    if config.per_file:
        return [_run([name], graph, config, kwargs) for name, graph in graphs.items()]
    return [_run(list(graphs), _merge(graphs.values()), config, kwargs)]


def _run(names, graph, config, kwargs):
    """One QA run over one graph, named by the datasets it was built from."""
    if config.inference:
        graph, _ = qa.infer_subclass_relations(graph)
    return qa.run_qa(
        graph,
        files_processed=names,
        source_iris=[dqv.dataset_iri(config.base_iri, name) for name in names],
        # A fresh checklist per run: each records the configuration it ran under.
        **{**kwargs, "checklist": qa.deepcopy_list(kwargs["checklist"])},
    )


def _run_kwargs(config, checklist, lint_config, rule_reasons):
    """The run_qa arguments a Config maps to, with the empty ones left at their defaults."""
    kwargs = {
        "checklist": checklist,
        "lint_config": lint_config,
        "rule_reasons": rule_reasons,
    }
    if config.imports:
        kwargs["local_imports"] = dict(config.imports)
    if config.ignore_imports:
        kwargs["ignore_imports"] = [str(i) for i in config.ignore_imports]
    if config.exclude_types:
        kwargs["exclude_types"] = [qa.expand_curie(str(t)) for t in config.exclude_types]
    if config.skip_object_of is not None:
        kwargs["skip_object_of"] = [qa.expand_curie(str(p), allow_wildcard=True) for p in config.skip_object_of]
    if config.uri_parser is not None:
        kwargs["uri_parser"] = config.uri_parser
    return kwargs


def _check_base_iri(base_iri):
    if base_iri is None:
        return
    try:
        dqv.check_base_uri(base_iri)
    except ValueError:
        raise ValueError(
            f"Config.base_iri must be an absolute IRI (e.g. https://example.org/qa/), got {base_iri!r}"
        ) from None


def _check_names():
    """Every check name that can appear in Config.checks, as it is written in .rdf-lint.yml."""
    return {qa.config_check_name(func, key) for _, func, _, key in qa.CHECKLIST}


def _select_checks(checks):
    """
    (checklist, lint_config, rule_reasons) for the requested checks.

    The names are the ones .rdf-lint.yml uses under `enable:`, so the selection — including
    the rules that pull in a check another one depends on — behaves exactly as the CLI's.
    """
    checklist = qa.deepcopy_list(qa.CHECKLIST)
    if checks is None:
        return checklist, None, {}

    valid = _check_names()
    requested, unknown = [], []
    for name in checks:
        canonical = str(name).removeprefix("check_").replace("_", "-")
        (requested if canonical in valid else unknown).append(canonical)
    if unknown:
        raise ValueError(
            f"Unknown check(s) in Config.checks: {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(sorted(valid))}"
        )

    lint_config = {"enable": [f"check_{name.replace('-', '_')}" for name in requested]}
    rule_reasons = {}
    checklist, _ = qa.lint_selection(lint_config, checklist, rule_reasons)
    return checklist, lint_config, rule_reasons


def _prepare(datasets):
    """
    {name: a private copy of the graph to check}.

    The checks remove instance data from the graph they run on, and inference adds to it,
    so a caller's graph is copied rather than worked on in place.
    """
    if not isinstance(datasets, Mapping):
        raise TypeError(f"datasets must be a mapping of name to graph, got {type(datasets).__name__}")
    if not datasets:
        raise ValueError("datasets is empty: nothing to lint")

    prepared = {}
    for name, value in datasets.items():
        if isinstance(value, rdflib.Graph):
            prepared[str(name)] = _copy(value)
        elif isinstance(value, str):
            prepared[str(name)] = rdflib.Graph().parse(data=value, format="turtle")
        else:
            raise TypeError(
                f"dataset {name!r} must be an rdflib.Graph or a Turtle string, got {type(value).__name__}"
            )
    return prepared


def _copy(graph):
    target = rdflib.Graph()
    target += graph
    _bind(target, graph)
    return target


def _merge(graphs):
    merged = rdflib.Graph()
    for graph in graphs:
        merged += graph
        _bind(merged, graph)
    return merged


def _bind(target, source):
    """Carry prefixes over: the hijacking and profiling checks report on declared prefixes."""
    for prefix, uri in source.namespace_manager.namespaces():
        try:
            target.namespace_manager.bind(prefix, uri)
        except Exception:
            pass  # a prefix that can't be rebound is not worth failing a run over
