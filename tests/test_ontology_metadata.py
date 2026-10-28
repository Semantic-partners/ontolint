import rdflib

from scripts.ontology_qa import run_qa
from tests.conftest import PREFIXES


def test_ontology_declared_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology ; rdfs:comment "A test ontology." .
    """)
    result = run_qa(g)
    assert result.get("Ontology without declaration").passed
    assert result.get("Ontology without description").passed


def test_ontology_not_declared_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    """)
    result = run_qa(g)
    check = result.get("Ontology without declaration")
    assert not check.passed
    assert check.count == 1


def test_ontology_declared_but_no_description_fails(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    """)
    result = run_qa(g)
    assert result.get("Ontology without declaration").passed
    check = result.get("Ontology without description")
    assert not check.passed
    assert check.count == 1


def test_rdfs_comment_accepted_as_description(make_graph):
    g = make_graph("""
    : a owl:Ontology ; rdfs:comment "Described via rdfs:comment." .
    """)
    result = run_qa(g)
    assert result.get("Ontology without description").passed


def test_dcterms_description_accepted(make_graph):
    g = make_graph("""
    : a owl:Ontology ; dcterms:description "Described via dcterms." .
    """)
    result = run_qa(g)
    assert result.get("Ontology without description").passed


def test_skos_definition_accepted_as_description(make_graph):
    g = make_graph("""
    : a owl:Ontology ; skos:definition "Described via skos:definition." .
    """)
    result = run_qa(g)
    assert result.get("Ontology without description").passed


# ── one file, one ontology: the "no more" direction (#97) ────────────────────
#
# check_owl_declaration covers "no less". These cover "no more", which has to be judged
# per source: in a merged run of several files, several declarations are normal.

def _dataset(sources):
    """A Dataset shaped as load_rdf builds one: {source IRI: Turtle} in its own context."""
    ds = rdflib.Dataset(default_union=True)
    for source, ttl in sources.items():
        g = rdflib.Graph()
        g.parse(data=PREFIXES + ttl, format='turtle')
        ds.graph(rdflib.URIRef(source)).__iadd__(g)
    return ds


def test_one_ontology_per_file_passes(make_graph):
    g = make_graph(""": a owl:Ontology ; rdfs:comment "Just the one." .""")
    assert run_qa(g).get("Multiple ontologies in one file").passed


def test_two_ontologies_in_one_file_fails(make_graph):
    g = make_graph("""
    <https://example.org/ont1#> a owl:Ontology ; rdfs:comment "One" .
    <https://example.org/ont2#> a owl:Ontology ; rdfs:comment "Two" .
    """)
    check = run_qa(g, files_processed=['both.ttl'],
                   source_iris=['https://example.org/input/both.ttl']).get("Multiple ontologies in one file")
    assert not check.passed
    assert check.count == 1
    # The violation has to name the file and both declarations, or the user is told a file
    # is wrong without being told which ontologies clash.
    (violation,) = check.violations
    assert str(violation.resource) == 'https://example.org/input/both.ttl'
    assert sorted(str(r) for r in violation.related) == [
        'https://example.org/ont1#', 'https://example.org/ont2#']


def test_one_ontology_per_file_is_judged_per_source_not_on_the_merge():
    # Two files, one ontology each. The merged graph holds two declarations, which is
    # correct; reading it as one source would make every multi-file run fail this check.
    ds = _dataset({
        'file:///a.ttl': """<https://example.org/ont1#> a owl:Ontology ; rdfs:comment "One" .""",
        'file:///b.ttl': """<https://example.org/ont2#> a owl:Ontology ; rdfs:comment "Two" .""",
    })
    result = run_qa(ds, files_processed=['a.ttl', 'b.ttl'])
    assert result.get("Multiple ontologies in one file").passed
    assert result.get("Ontology without declaration").passed


def test_one_offending_file_among_several_is_named():
    ds = _dataset({
        'file:///good.ttl': """<https://example.org/ont1#> a owl:Ontology ; rdfs:comment "One" .""",
        'file:///bad.ttl': """
            <https://example.org/ont2#> a owl:Ontology ; rdfs:comment "Two" .
            <https://example.org/ont3#> a owl:Ontology ; rdfs:comment "Three" .
        """,
    })
    check = run_qa(ds, files_processed=['good.ttl', 'bad.ttl']).get("Multiple ontologies in one file")
    assert not check.passed
    assert check.count == 1
    assert str(check.violations[0].resource) == 'file:///bad.ttl'


def test_the_declaration_count_never_goes_negative(make_graph):
    # The bug in #97: one file with two declarations took ontologyNotDeclared to -1, which
    # matched neither violation branch, so the Markdown said PASS while CheckResult (count
    # == 0) called it a failure and the build failed with no stated reason.
    g = make_graph("""
    <https://example.org/ont1#> a owl:Ontology ; rdfs:comment "One" .
    <https://example.org/ont2#> a owl:Ontology ; rdfs:comment "Two" .
    """)
    check = run_qa(g, files_processed=['both.ttl']).get("Ontology without declaration")
    assert check.count == 0
    assert check.passed
