"""
Ontolint's programmatic entry point: lint graphs you already hold, get a graph back.

The checks have always worked on an `rdflib.Graph`; this module exposes that layer
without the command line, so a caller whose ontologies are already in memory doesn't
have to serialise them to a temporary directory and read a report file back.

    import rdflib
    from ontolint import Config, lint

    report = lint(
        {"https://example.org/activities": activities_graph,
         "https://example.org/parties":    parties_graph},
        config=Config(per_file=True, imports={"https://schema.org/": schema_graph}),
    )

`report` is a DQV graph: the same one the CLI writes with --dqv-dir, built by the same
run that the CLI performs (`ontology_qa.lint_graph`).
"""

from collections.abc import Mapping
from typing import TypeAlias

import rdflib

from scripts import dqv
from scripts import ontology_qa as qa
from scripts.ontology_qa import IRI, Config

__all__ = ["Config", "lint"]

# A graph to check, or the Turtle to parse into one.
Dataset: TypeAlias = rdflib.Graph | str


def lint(datasets: Mapping[IRI, Dataset], config: Config | None = None) -> rdflib.Graph:
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
    configuration the run used. It also carries, per dataset, an `ontolint-conformance`
    measurement whose `olq:conforms` says whether every executed check passed and whose
    `dqv:value` counts those that didn't — which is how you get a pass/fail or an exit
    code out of it.

    The graphs you pass are never modified: each is copied before inference runs and
    before the checks exclude instance data from it.
    """
    config = config or Config()
    graphs = _prepare(datasets)
    _check_base_iri(config.base_iri)
    # Resolved once, so an unknown check name is rejected before anything runs.
    checklist, lint_config, rule_reasons = qa.select_checks(config.checks)
    provenance = {'lint_config': lint_config, 'rule_reasons': rule_reasons}

    def run(graph, names):
        return qa.lint_graph(graph, names, config, checklist=checklist, provenance=provenance,
                             source_iris=[dqv.dataset_iri(config.base_iri, name) for name in names])

    if config.per_file:
        results = [run(graph, [name]) for name, graph in graphs.items()]
    else:
        results = [run(_merge(graphs.values()), list(graphs))]
    return dqv.build_dqv_graph(results, base_uri=config.base_iri)


def _check_base_iri(base_iri):
    if base_iri is None:
        return
    try:
        dqv.check_base_uri(str(base_iri))
    except ValueError:
        raise ValueError(
            f"Config.base_iri must be an absolute IRI (e.g. https://example.org/qa/), got {base_iri!r}"
        ) from None


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
