import rdflib
import scripts.ontology_qa as qa_module
from scripts.ontology_qa import check_undefined_terms

CHECK_NAME = "Undefined terms"
CHECK_KEY = "undefinedTerms"
# Matches the @prefix : declaration in conftest.py
LOCAL_NS = "http://example.org#"

# Standard-vocabulary namespaces present in many ontologies.
# Passed to fail_on in mock tests so they are skipped rather than flagged,
# letting each test focus purely on the namespace under test.
STD_NAMESPACES = frozenset({
    str(rdflib.RDF),
    str(rdflib.RDFS),
    str(rdflib.OWL),
    "http://www.w3.org/ns/shacl#",
    "http://www.w3.org/2004/02/skos/core#",
    "http://purl.org/dc/terms/",
})


def _in_metrics(ont_uri=LOCAL_NS):
    """Minimal in_metrics for direct invocation of check_undefined_terms."""
    return {
        "filesProcessed": ["test.ttl"],
        "ontologyURI": ([rdflib.URIRef(ont_uri)] if ont_uri else []),
    }


def _call(graph, ont_uri=LOCAL_NS, verbose=False):
    """Call check_undefined_terms directly and return (metrics, violations, log)."""
    metrics, violations, log, _, _ = check_undefined_terms(
        _in_metrics(ont_uri), graph, CHECK_NAME, CHECK_KEY, 1, 0, verbose
    )
    return metrics, violations, log


def _mock_graph_class(ns_subjects=None, fail_on=None):
    """
    Returns a replacement for rdflib.Graph that controls remote-fetch behaviour.

    ns_subjects: {namespace_uri: [subject_uri, ...]} returned by a successful parse
    fail_on:     set of namespace URIs where parse() raises ConnectionError
    """
    ns_subjects = ns_subjects or {}
    fail_on = fail_on or set()

    class MockGraph:
        def __init__(self):
            self._triples = []

        def parse(self, uri, **kwargs):
            if uri in fail_on:
                raise ConnectionError(f"Simulated failure: {uri}")
            for s in ns_subjects.get(uri, []):
                self._triples.append(
                    (rdflib.URIRef(s), rdflib.RDF.type, rdflib.OWL.Class)
                )

        def __iter__(self):
            return iter(self._triples)

        def __iadd__(self, other):
            return self

        def __len__(self):
            return len(self._triples)

    return MockGraph


# ── No violations ─────────────────────────────────────────────────────────────

def test_all_local_terms_declared_passes(make_graph):
    """Every term in the local namespace is a subject — nothing is undefined."""
    g = make_graph("""
    : a owl:Ontology .
    :Cat a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :Cat .
    """)
    metrics, _, _ = _call(g)
    assert metrics[CHECK_KEY] == 0


def test_term_used_as_both_subject_and_object_not_flagged(make_graph):
    """:Animal is the target of rdfs:subClassOf AND is declared as owl:Class."""
    g = make_graph("""
    : a owl:Ontology .
    :Animal a owl:Class .
    :Cat a owl:Class ; rdfs:subClassOf :Animal .
    """)
    metrics, _, _ = _call(g)
    assert metrics[CHECK_KEY] == 0


# ── Local namespace violations ────────────────────────────────────────────────

def test_local_undeclared_range_fails(make_graph):
    """:Fur is used as rdfs:range but never declared as a subject."""
    g = make_graph("""
    : a owl:Ontology .
    :Cat a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :Fur .
    """)
    metrics, violations, _ = _call(g)
    assert metrics[CHECK_KEY] == 1
    assert LOCAL_NS + "Fur" in violations[CHECK_KEY]


def test_local_undeclared_domain_fails(make_graph):
    """:Animal is used as rdfs:domain but never declared."""
    g = make_graph("""
    : a owl:Ontology .
    :hasFur a owl:ObjectProperty ; rdfs:domain :Animal .
    """)
    metrics, violations, _ = _call(g)
    assert metrics[CHECK_KEY] >= 1
    assert LOCAL_NS + "Animal" in violations[CHECK_KEY]


def test_multiple_local_undefined_terms_all_counted(make_graph):
    """Two distinct local terms used but never declared — count must be exactly 2."""
    g = make_graph("""
    : a owl:Ontology .
    :Cat a owl:Class .
    :hasFur a owl:ObjectProperty ;
        rdfs:range :Fur ;
        rdfs:domain :Mammal .
    """)
    metrics, violations, _ = _call(g)
    assert metrics[CHECK_KEY] == 2
    assert LOCAL_NS + "Fur" in violations[CHECK_KEY]
    assert LOCAL_NS + "Mammal" in violations[CHECK_KEY]


def test_undefined_terms_appear_in_violations_string(make_graph):
    """The violations dict entry must contain the full URI of the undefined term."""
    g = make_graph("""
    : a owl:Ontology .
    :hasFur a owl:ObjectProperty ; rdfs:range :MissingClass .
    """)
    _, violations, _ = _call(g)
    assert LOCAL_NS + "MissingClass" in violations[CHECK_KEY]


# ── No owl:Ontology declaration ───────────────────────────────────────────────

def test_no_ontology_declaration_logs_local_namespace_warning(make_graph):
    """Without owl:Ontology the local namespace is unknown — a warning must appear."""
    g = make_graph("""
    :Cat a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :Fur .
    """)
    _, _, log = _call(g, ont_uri=None)
    assert "WARNING" in log
    assert "local namespace" in log.lower()


# ── Remote fetch — mocked ─────────────────────────────────────────────────────

def test_remote_term_defined_in_fetched_graph_passes(monkeypatch):
    """A predicate from a fetchable remote namespace IS found there — no violation."""
    MYNS = rdflib.Namespace("http://myns.example.org#")

    g = rdflib.Graph()
    g.add((rdflib.URIRef(LOCAL_NS), rdflib.RDF.type, rdflib.OWL.Ontology))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), rdflib.RDF.type, rdflib.OWL.Class))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), MYNS["color"], rdflib.Literal("grey")))

    monkeypatch.setattr(
        qa_module.rdflib, "Graph",
        _mock_graph_class(
            ns_subjects={str(MYNS): [str(MYNS["color"])]},
            fail_on=STD_NAMESPACES,
        ),
    )
    metrics, _, _ = _call(g)
    assert metrics[CHECK_KEY] == 0


def test_remote_term_absent_from_fetched_graph_fails(monkeypatch):
    """A predicate from a fetchable namespace is NOT defined there — violation."""
    MYNS = rdflib.Namespace("http://myns.example.org#")

    g = rdflib.Graph()
    g.add((rdflib.URIRef(LOCAL_NS), rdflib.RDF.type, rdflib.OWL.Ontology))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), rdflib.RDF.type, rdflib.OWL.Class))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), MYNS["madeUpProp"], rdflib.Literal("x")))

    monkeypatch.setattr(
        qa_module.rdflib, "Graph",
        _mock_graph_class(
            ns_subjects={str(MYNS): []},  # namespace fetched but defines nothing
            fail_on=STD_NAMESPACES,
        ),
    )
    metrics, violations, _ = _call(g)
    assert metrics[CHECK_KEY] == 1
    assert str(MYNS["madeUpProp"]) in violations[CHECK_KEY]


def test_remote_fetch_failure_skips_those_terms(monkeypatch):
    """When a namespace cannot be fetched its terms are skipped, not flagged."""
    MYNS = rdflib.Namespace("http://unreachable.example.org#")

    g = rdflib.Graph()
    g.add((rdflib.URIRef(LOCAL_NS), rdflib.RDF.type, rdflib.OWL.Ontology))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), rdflib.RDF.type, rdflib.OWL.Class))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), MYNS["prop"], rdflib.Literal("v")))

    monkeypatch.setattr(
        qa_module.rdflib, "Graph",
        _mock_graph_class(fail_on=STD_NAMESPACES | {str(MYNS)}),
    )
    metrics, _, _ = _call(g)
    assert metrics[CHECK_KEY] == 0


def test_remote_fetch_failure_listed_in_log(monkeypatch):
    """The log must identify which namespaces could not be fetched."""
    BADNS = rdflib.Namespace("http://bad.example.org#")

    g = rdflib.Graph()
    g.add((rdflib.URIRef(LOCAL_NS), rdflib.RDF.type, rdflib.OWL.Ontology))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), BADNS["prop"], rdflib.Literal("x")))

    monkeypatch.setattr(
        qa_module.rdflib, "Graph",
        _mock_graph_class(fail_on=STD_NAMESPACES | {str(BADNS)}),
    )
    _, _, log = _call(g)
    assert "bad.example.org" in log
    assert "WARNING" in log


def test_local_undefined_reported_even_when_remote_fetch_fails(monkeypatch):
    """A local dangling ref is still a violation even if a remote namespace fails."""
    MYNS = rdflib.Namespace("http://unreachable.example.org#")

    g = rdflib.Graph()
    g.add((rdflib.URIRef(LOCAL_NS), rdflib.RDF.type, rdflib.OWL.Ontology))
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), rdflib.RDF.type, rdflib.OWL.Class))
    # :UndeclaredLocal is a local dangling ref
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), rdflib.RDFS.subClassOf,
           rdflib.URIRef(LOCAL_NS + "UndeclaredLocal")))
    # MYNS term whose namespace fails to fetch — must be skipped
    g.add((rdflib.URIRef(LOCAL_NS + "Cat"), MYNS["prop"], rdflib.Literal("x")))

    monkeypatch.setattr(
        qa_module.rdflib, "Graph",
        _mock_graph_class(fail_on=STD_NAMESPACES | {str(MYNS)}),
    )
    metrics, violations, _ = _call(g)
    assert metrics[CHECK_KEY] == 1
    assert LOCAL_NS + "UndeclaredLocal" in violations[CHECK_KEY]
    assert str(MYNS["prop"]) not in violations[CHECK_KEY]
