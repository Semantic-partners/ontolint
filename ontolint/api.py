"""
Ontolint's programmatic entry point: lint graphs you already hold, get a graph back.

The checks have always worked on an `rdflib.Graph`; this module exposes that layer
without the command line, so a caller whose ontologies are already in memory doesn't
have to serialise them to a temporary directory and read a report file back.

    import rdflib
    from ontolint import Config, lint

    report = lint(
        [activities_graph, parties_graph],
        config=Config(per_file=True, imports=[schema_graph]),
    )

Neither the datasets nor the vocabularies need naming: each is identified by what it
declares and defines. Pass a mapping where you want to name one yourself.

`report` is a DQV graph: the same one the CLI writes with --dqv-dir, built by the same
run that the CLI performs (`ontology_qa.lint_graph`).
"""

from collections.abc import Iterable, Mapping
from typing import TypeAlias

import rdflib

from scripts import dqv, graphutil
from scripts import ontology_qa as qa
from scripts.ontology_qa import IRI, Config

# The whole public surface: two names, and nothing else here is supported.
#
#   Config  — every setting a run takes, with its default (defined in
#             scripts.ontology_qa, because the CLI builds one too; it moves here when
#             that module is split for packaging). `help(ontolint.Config)` lists the
#             fields, the readme tabulates them, and tests/test_api.py pins both.
#   lint    — run the checks over named graphs, return the DQV report as a graph.
#
# Anything added to __all__ is a promise to keep, so prefer putting new behaviour on the
# engine side (scripts.ontology_qa), where the CLI can use it too.
__all__ = ["Config", "lint"]

# Config is defined in the engine module so both front ends can build one, but `ontolint`
# is where it is published: say so, or help(), pickle and generated docs all send readers
# to an implementation module. Remove once the module is split and Config lives here.
Config.__module__ = "ontolint"

# A graph to check, or the Turtle to parse into one.
Dataset: TypeAlias = rdflib.Graph | str
# One of those, several of them, or several under names you choose.
Datasets: TypeAlias = Dataset | Iterable[Dataset] | Mapping[IRI, Dataset]


def lint(datasets: Datasets, config: Config | None = None) -> rdflib.Graph:
    """
    Check the given graphs and return the results as a DQV graph.

    Pass one graph, several of them, or a mapping of names to graphs:

        lint(graph)                                   # one
        lint([activities, parties])                   # several
        lint({"https://example.org/parties": parties})  # named

    **You only need to name a graph that doesn't declare its own `owl:Ontology`**, because
    a declared ontology IRI is what the dataset is reported under in any case — so naming
    them yourself means extracting what ontolint reads anyway. An unnamed graph that
    declares no ontology falls back to `unnamed-1`, `unnamed-2` by position, which is
    stable only for the same order; name those if you want to compare runs.

    Ontolint's rule is one file, one ontology. If two graphs declare the same
    `owl:Ontology` IRI, that is reported in the graph as a `duplicate-ontology-iri`
    finding naming both inputs, and every other check still runs.

    A name that is itself an absolute IRI is used as the dataset's identity as it stands,
    so the same dataset is identified the same way across runs, machines and callers. Any
    other name is a local label, minted into an IRI under `base_iri` and meaningful only
    within these reports.

    A graph may also be given as a Turtle string, which is parsed for you.

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
    prepared = _prepare(datasets)
    _check_base_iri(config.base_iri)
    # One file, one ontology: two inputs declaring the same owl:Ontology IRI is a finding,
    # not a reason to refuse. Computed here because merging them would hide it.
    duplicates = qa.duplicate_ontology_iris(qa.declared_ontology_sources(
        (dqv.dataset_iri(config.base_iri, source), graph) for _, source, graph in prepared))
    # Resolved once, so an unknown check name is rejected before anything runs.
    checklist, lint_config, rule_reasons = qa.select_checks(config.checks)
    provenance = {'lint_config': lint_config, 'rule_reasons': rule_reasons}

    def run(graph, names, context_imports=None):
        return qa.lint_graph(graph, names, config, checklist=checklist, provenance=provenance,
                             context_imports=context_imports,
                             source_iris=[dqv.dataset_iri(config.base_iri, name) for name in names])

    if config.per_file:
        # Each dataset resolves against the others of the same call, as a per-file CLI run
        # resolves against the files it is not checking (#108). A dataset answers only for
        # the ontology it declares, so one cannot shadow a vocabulary by minting into it.
        results = [run(graph, [name], _siblings(prepared, name) if config.resolve_siblings else None)
                   for name, _, graph in prepared]
    else:
        results = [run(_merge(graph for *_, graph in prepared), [name for name, *_ in prepared])]
    return dqv.build_dqv_graph(results, base_uri=config.base_iri,
                               duplicate_ontologies=duplicates)


def _siblings(prepared, name):
    """{namespace: the dataset that declares it} for every dataset of this call but one."""
    context = {}
    for other, _, graph in prepared:
        if other == name:
            continue
        for namespace in qa.ontology_iris(graph):
            context.setdefault(namespace, qa.RunInput(other, graph))
    return context


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
    [(name, source, a private copy of the graph to check)], whichever way they were passed.

    The checks remove instance data from the graph they run on, and inference adds to it,
    so a caller's graph is copied rather than worked on in place.
    """
    prepared = []
    for index, (name, value) in enumerate(_items(datasets), start=1):
        graph = _as_graph(name, value)
        # The source is how the caller referred to this input, which is what a set-level
        # finding has to name. It differs from the dataset name for an unnamed graph: that
        # is named after the ontology it declares, so two inputs declaring the same one
        # would otherwise be reported as the same input twice.
        source = str(name) if name is not None else f"unnamed-{index}"
        prepared.append((str(name) if name is not None else _derive_name(graph, index),
                         source, graph))
    return prepared


def _items(datasets):
    """(name|None, value) pairs for a single dataset, a sequence of them, or a mapping."""
    # A Turtle string is itself iterable, so the single-dataset forms are recognised first.
    if isinstance(datasets, (rdflib.Graph, str)):
        return [(None, datasets)]
    if isinstance(datasets, Mapping):
        items = list(datasets.items())
    elif isinstance(datasets, Iterable):
        items = [(None, value) for value in datasets]
    else:
        raise TypeError(
            "datasets must be a graph, an iterable of graphs, or a mapping of name to graph, "
            f"got {type(datasets).__name__}"
        )
    if not items:
        raise ValueError("datasets is empty: nothing to lint")
    return items


def _as_graph(name, value):
    if isinstance(value, rdflib.Graph):
        return _copy(value)
    if isinstance(value, str):
        return rdflib.Graph().parse(data=value, format="turtle")
    raise TypeError(
        f"dataset {name if name is not None else ''!r} must be an rdflib.Graph or a Turtle "
        f"string, got {type(value).__name__}"
    )


def _derive_name(graph, index):
    """
    What an unnamed graph is called: the ontology it declares, else its position.

    A declared owl:Ontology IRI is what the dataset is reported under anyway, so using it
    saves the caller extracting it. Position is only a fallback — it is stable for the same
    order and no more, which is why the caller should name such graphs.
    """
    declared = qa.ontology_iris(graph)
    return declared[0] if declared else f"unnamed-{index}"


def _copy(graph):
    target = rdflib.Graph()
    target += graph
    return graphutil.copy_namespaces(target, graph)


def _merge(graphs):
    merged = rdflib.Graph()
    for graph in graphs:
        merged += graph
        graphutil.copy_namespaces(merged, graph)
    return merged
