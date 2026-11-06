# Graph helpers with no ontolint knowledge in them.
#
# They live apart from ontology_qa and dqv so both can use them without one importing the
# other, and so the next module that needs a graph doesn't grow a third copy.

"""Small rdflib helpers: making a graph with prefixes, and carrying prefixes between graphs."""

import rdflib


def bound_graph(prefixes):
    """
    An empty graph with the given (prefix, namespace) pairs bound.

    Worth doing for a graph that may be read on its own — a subgraph of a report, say —
    since an unbound graph serialises as ns1:, ns2:, … and stops being legible.
    """
    g = rdflib.Graph()
    for prefix, namespace in prefixes:
        g.bind(prefix, namespace)
    return g


def copy_namespaces(target, source):
    """
    Carry a graph's prefixes over to another, and return the target.

    `+=` copies triples but not bindings, and in ontolint the prefixes are not decoration:
    the namespace-hijacking and profiling checks report on what the input declared.
    """
    for prefix, uri in source.namespace_manager.namespaces():
        try:
            target.namespace_manager.bind(prefix, uri)
        except Exception:
            pass  # a prefix that can't be rebound is not worth failing a run over
    return target
