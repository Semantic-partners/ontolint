"""
Where a term's definition comes from, when it is not in the graph being checked.

In order of precedence: the project's own imports.local, another input of the same run
(sibling_imports, #108), and the vocabularies bundled with ontolint. Two checks consult
this — owl-imports and undefined-terms — and they are the only ones that look outside the
graph they were given. Everything here answers "which graph defines this namespace?" and
nothing decides what to do with the answer.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import rdflib

from .terms import get_namespace, iri_key, ontology_iris


# ── Bundled vocabularies ─────────────────────────────────────────────────────
# Standard vocabularies shipped with ontolint (vocabularies/, see its README.md). Each is
# added to imports.local, so their namespaces and owl:imports resolve offline and their
# terms are validated by the undefined-terms check.
#
# The DCAT catalog is the single starting point for discovery: which vocabularies are
# bundled, their namespaces, and where each file is (its dcat:downloadURL, resolved
# relative to the catalog). Found relative to this module so the CLI and the composite
# action work from any working directory.
VOCAB_CATALOG = Path(__file__).resolve().parent / 'vocabularies' / 'catalog.ttl'


@lru_cache(maxsize=1)
def bundled_vocabularies():
    """
    {namespace: absolute file path} for every vocabulary in the VOCAB_CATALOG DCAT catalog:
    each dcat:Dataset gives its namespace (vann:preferredNamespaceUri) and a
    dcat:Distribution whose dcat:downloadURL is the file, relative to the catalog.
    """
    catalog = rdflib.Graph().parse(VOCAB_CATALOG, format='turtle')
    vocabularies = {}
    for dataset in sorted(catalog.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset)):
        namespace = catalog.value(dataset, rdflib.VANN.preferredNamespaceUri)
        url = catalog.value(catalog.value(dataset, rdflib.DCAT.distribution), rdflib.DCAT.downloadURL)
        if namespace is None or url is None:
            raise ValueError(f"{dataset} in {VOCAB_CATALOG} needs vann:preferredNamespaceUri "
                             "and a dcat:distribution with a dcat:downloadURL")
        vocabularies[str(namespace)] = str(Path(url2pathname(urlparse(str(url)).path)).resolve())
    return vocabularies


@lru_cache(maxsize=1)
def bundled_datasets():
    """{namespace: catalog dcat:Dataset IRI} for every vocabulary in VOCAB_CATALOG."""
    catalog = rdflib.Graph().parse(VOCAB_CATALOG, format='turtle')
    return {str(catalog.value(d, rdflib.VANN.preferredNamespaceUri)): str(d)
            for d in catalog.subjects(rdflib.RDF.type, rdflib.DCAT.Dataset)}


def defined_namespaces(graph):
    """
    Every namespace a vocabulary graph defines terms in: the owl:Ontology IRIs it declares,
    and the namespace of each of its subjects.

    This is what an unkeyed entry in Config.imports is registered under, so a caller can
    hand over a vocabulary without working out which namespace to file it against — and a
    vocabulary spanning several is registered for all of them, not a guessed main one.
    """
    ontologies = set(ontology_iris(graph))
    namespaces = set(ontologies)
    for subject in graph.subjects(unique=True):
        # The ontology IRI's own namespace is skipped: <.../core> sits in <.../>, and
        # claiming that would register this vocabulary for every sibling beside it.
        if isinstance(subject, rdflib.URIRef) and str(subject) not in ontologies:
            namespace = get_namespace(str(subject))
            if namespace:
                namespaces.add(namespace)
    return namespaces


def local_imports_from(imports):
    """
    Config.imports as the {namespace: vocabulary} mapping the checks take.

    A mapping is used as given. An unkeyed iterable of vocabularies is keyed by what each
    one defines (see defined_namespaces); a path is parsed to find out.
    """
    if not imports:
        return {}
    if isinstance(imports, Mapping):
        return dict(imports)
    keyed = {}
    for vocabulary in imports:
        graph = vocabulary if isinstance(vocabulary, rdflib.Graph) else _parse_local(vocabulary)
        for namespace in defined_namespaces(graph):
            keyed[namespace] = graph
    return keyed


def merge_local_imports(local_imports=None):
    """
    Bundled vocabularies plus the project's imports.local, keyed by iri_key(); the project wins.

    A value is a file path, or an already-loaded rdflib.Graph when the caller supplied one
    through the programmatic API (see ontolint.Config.imports).
    """
    merged = {iri_key(ns): path for ns, path in bundled_vocabularies().items()}
    merged.update({iri_key(k): v for k, v in (local_imports or {}).items()})
    return merged


def _is_bundled(source):
    """Whether a file is one of the catalogued vocabularies (by the catalog, not by directory)."""
    if isinstance(source, (rdflib.Graph, RunInput)):
        return False
    return str(Path(source).resolve()) in bundled_vocabularies().values()


@lru_cache(maxsize=None)
def _parse_bundled(path):
    """Parse a bundled vocabulary once per process (treated as read-only)."""
    return rdflib.Graph().parse(path)


@dataclass(frozen=True)
class RunInput:
    """
    Another input of the same invocation, registered as something to resolve against.

    It carries what the input is called as well as its graph, so a report can say where a
    definition came from: a file path from the CLI, a dataset name from the API. Without
    that it would be indistinguishable from a vocabulary graph a caller handed over, which
    is a different thing and reads differently.
    """
    source: str
    graph: rdflib.Graph


def _parse_local(source):
    """The graph for an imports.local entry: a caller-supplied graph, or a file to parse."""
    if isinstance(source, RunInput):
        return source.graph
    if isinstance(source, rdflib.Graph):
        return source
    return _parse_bundled(source) if _is_bundled(source) else rdflib.Graph().parse(source)


def _describe_local(source):
    if isinstance(source, RunInput):
        return f"another input: `{source.source}`"
    if isinstance(source, rdflib.Graph):
        return f"graph supplied by the caller ({len(source)} triples)"
    return f"bundled: `{Path(source).name}`" if _is_bundled(source) else f"local file: `{source}`"


def sibling_imports(parsed, run_inputs):
    """
    {namespace: graph} for the inputs of this invocation that this run is not checking.

    A family of ontologies developed together refers to itself before it is published, and
    those references resolve against the run rather than the network — which is the whole
    of #108. They are registered exactly as a bundled vocabulary is, so nothing downstream
    needs to know where the definition came from.

    An input speaks for the ontology it *declares*, and for nothing else. Every namespace it
    merely has subjects in — which is what defined_namespaces() gives, and what an input
    handed over as a vocabulary is registered for — would let one input shadow a real
    vocabulary by hijacking its namespace, and the inputs here are the files under test:
    tests/example_failure.ttl mints a term in the SKOS namespace, and registering it for
    SKOS made skos:prefLabel undefined in the file beside it.
    """
    context = {}
    for path, (success, graph, _) in parsed.items():
        if not success or path in run_inputs:
            continue
        for namespace in ontology_iris(graph):
            context.setdefault(namespace, RunInput(path, graph))
    return context
