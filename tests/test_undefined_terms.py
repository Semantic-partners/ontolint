import rdflib
from ontolint.ontology_qa import run_qa

CHECK_NAME = "Undefined terms"


def _no_fetch(uri):
    raise Exception(f"no network in tests: {uri}")


# ── Local namespace ───────────────────────────────────────────────────────────

def test_no_external_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog a owl:Class .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_local_undefined_term_fails(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_local_predicate_not_declared_fails(make_graph):
    # :livesIn is used as a predicate but never declared as a subject
    g = make_graph("""
    : a owl:Ontology .
    :Dog :livesIn :Kennel .
    :Dog a owl:Class .
    :Kennel a owl:Class .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_local_predicate_declared_passes(make_graph):
    # :livesIn is used as a predicate and also declared as a subject
    g = make_graph("""
    : a owl:Ontology .
    :Dog :livesIn :Kennel .
    :Dog a owl:Class .
    :Kennel a owl:Class .
    :livesIn a owl:ObjectProperty .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_multiple_local_undefined_terms_count(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    :Cat rdfs:subClassOf :Reptile .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 2


def test_mix_of_defined_and_undefined_local_terms(make_graph):
    # :Mammal is declared so it passes; :Reptile is not so it is flagged
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    :Mammal a owl:Class .
    :Cat rdfs:subClassOf :Reptile .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


# ── Remote namespace ──────────────────────────────────────────────────────────

def test_remote_term_found_passes(make_graph):
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "http://remote.example.org#":
            g.add((
                rdflib.URIRef("http://remote.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_remote_namespace_resolves_but_term_absent_fails(make_graph):
    def fake_parser(uri):
        if uri == "http://remote.example.org#":
            return rdflib.Graph()
        raise Exception(f"no network in tests: {uri}")

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


def test_unresolvable_remote_namespace_is_skipped(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_https_remote_term_found_passes(make_graph):
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "https://remote.example.org#":
            g.add((
                rdflib.URIRef("https://remote.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <https://remote.example.org#Mammal> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_multiple_remote_namespaces_partial_resolution(make_graph):
    # Namespace A resolves with term found — passes
    # Namespace B resolves but term is absent — flagged
    def fake_parser(uri):
        g = rdflib.Graph()
        if uri == "http://a.example.org#":
            g.add((
                rdflib.URIRef("http://a.example.org#Mammal"),
                rdflib.RDF.type,
                rdflib.OWL.Class,
            ))
        elif uri == "http://b.example.org#":
            pass  # resolves but returns empty graph
        else:
            raise Exception(f"no network in tests: {uri}")
        return g

    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf <http://a.example.org#Mammal> .
    :Gecko rdfs:subClassOf <http://b.example.org#Reptile> .
    """)
    check = run_qa(g, uri_parser=fake_parser).get(CHECK_NAME)
    assert not check.passed
    assert check.count == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_ontology_declaration_local_undefined_not_flagged(make_graph):
    # Without owl:Ontology the local namespace is unknown, so :Mammal cannot
    # be identified as local. It falls through to an unresolvable remote
    # namespace and is skipped rather than flagged.
    g = make_graph("""
    :Dog a owl:Class .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert check.passed
    assert check.count == 0


def test_violation_elements_lists_undefined_uri(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog rdfs:subClassOf :Mammal .
    """)
    check = run_qa(g, uri_parser=_no_fetch).get(CHECK_NAME)
    assert "http://example.org#Mammal" in check.elements
