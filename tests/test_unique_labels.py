from scripts.ontology_qa import run_qa


# ── Classes ───────────────────────────────────────────────────────────────────

def test_classes_with_unique_labels_pass(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Cat" .
    :Dog a owl:Class ; rdfs:label "Dog" .
    """)
    assert run_qa(g).get("Non-Unique Class Labels").passed


def test_two_classes_sharing_a_label_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Animal" .
    :Dog a owl:Class ; rdfs:label "Animal" .
    """)
    check = run_qa(g).get("Non-Unique Class Labels")
    assert not check.passed
    assert check.count == 1
    assert "Animal" in check.elements


def test_same_label_different_language_tags_passes(make_graph):
    # Labels with distinct language tags are not considered duplicates by the SPARQL query
    # because the language tag is part of the literal value matched by the query.
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Animal"@en .
    :Dog a owl:Class ; rdfs:label "Animal"@fr .
    """)
    assert run_qa(g).get("Non-Unique Class Labels").passed


def test_three_classes_one_duplicate_label_fails(make_graph):
    g = make_graph("""
    :A a owl:Class ; rdfs:label "Shared" .
    :B a owl:Class ; rdfs:label "Shared" .
    :C a owl:Class ; rdfs:label "Unique" .
    """)
    check = run_qa(g).get("Non-Unique Class Labels")
    assert not check.passed


# ── Properties ────────────────────────────────────────────────────────────────

def test_properties_with_unique_labels_pass(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:label "Has Fur" .
    :hasTail a owl:ObjectProperty ; rdfs:label "Has Tail" .
    """)
    assert run_qa(g).get("Non-Unique Property Labels").passed


def test_two_properties_sharing_a_label_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:label "Has Feature" .
    :hasTail a owl:ObjectProperty ; rdfs:label "Has Feature" .
    """)
    check = run_qa(g).get("Non-Unique Property Labels")
    assert not check.passed
    assert check.count == 1
    assert "Has Feature" in check.elements


# ── NodeShapes ────────────────────────────────────────────────────────────────

def test_node_shapes_with_unique_labels_pass(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; sh:name "Cat Shape" .
    :DogShape a sh:NodeShape ; sh:name "Dog Shape" .
    """)
    assert run_qa(g).get("Non-Unique NodeShape Labels").passed


def test_two_node_shapes_sharing_a_label_fails(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; rdfs:label "Animal Shape" .
    :DogShape a sh:NodeShape ; rdfs:label "Animal Shape" .
    """)
    check = run_qa(g).get("Non-Unique NodeShape Labels")
    assert not check.passed
    assert check.count == 1
    assert "Animal Shape" in check.elements


# ── PropertyShapes ────────────────────────────────────────────────────────────

def test_property_shapes_with_unique_labels_pass(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape ; sh:name "Has Fur" .
    :hasTailShape a sh:PropertyShape ; sh:name "Has Tail" .
    """)
    assert run_qa(g).get("Non-Unique PropertyShape Labels").passed


def test_two_property_shapes_sharing_a_label_fails(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape ; rdfs:label "Has Feature" .
    :hasTailShape a sh:PropertyShape ; rdfs:label "Has Feature" .
    """)
    check = run_qa(g).get("Non-Unique PropertyShape Labels")
    assert not check.passed
    assert check.count == 1
