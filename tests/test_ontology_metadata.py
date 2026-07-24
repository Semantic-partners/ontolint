from ontolint.ontology_qa import run_qa


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
