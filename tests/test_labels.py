from scripts.ontology_qa import run_qa


# ── Classes ──────────────────────────────────────────────────────────────────

def test_class_with_rdfs_label_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Cat" .
    """)
    assert run_qa(g).get("Class without label").passed


def test_class_with_skos_pref_label_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; skos:prefLabel "Cat" .
    """)
    assert run_qa(g).get("Class without label").passed


def test_class_without_label_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    """)
    check = run_qa(g).get("Class without label")
    assert not check.passed
    assert check.count == 1
    assert "Cat" in check.elements


def test_one_of_two_classes_missing_label_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:label "Cat" .
    :Dog a owl:Class .
    """)
    check = run_qa(g).get("Class without label")
    assert not check.passed
    assert check.count == 1


def test_class_with_rdfs_label_verbose_is_printed(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; skos:prefLabel "Cat-label" .
    """)
    logs = run_qa(g, verbose=True).logs
    assert any("Cat-label" in log for log in logs)


# ── Properties ───────────────────────────────────────────────────────────────

def test_property_with_rdfs_label_passes(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:label "Has Fur" .
    """)
    assert run_qa(g).get("Property without label").passed


def test_property_with_skos_pref_label_passes(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; skos:prefLabel "Has Fur" .
    """)
    assert run_qa(g).get("Property without label").passed


def test_property_without_label_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty .
    """)
    check = run_qa(g).get("Property without label")
    assert not check.passed
    assert check.count == 1
    assert "hasFur" in check.elements


def test_datatype_property_without_label_fails(make_graph):
    g = make_graph("""
    :hasAge a owl:DatatypeProperty .
    """)
    check = run_qa(g).get("Property without label")
    assert not check.passed


def test_property_with_rdfs_label_verbose_is_printed(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:label "Has Fur" .
    """)
    logs = run_qa(g, verbose=True).logs
    assert any("Has Fur" in log for log in logs)


# ── NodeShapes ────────────────────────────────────────────────────────────────

def test_node_shape_with_rdfs_label_passes(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; rdfs:label "Cat Shape" .
    """)
    assert run_qa(g).get("NodeShape without label").passed


def test_node_shape_without_label_fails(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape .
    """)
    check = run_qa(g).get("NodeShape without label")
    assert not check.passed
    assert check.count == 1
    assert "CatShape" in check.elements


def test_node_shape_with_rdfs_label_verbose_is_printed(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; rdfs:label "Cat Shape" .
    """)
    logs = run_qa(g, verbose=True).logs
    assert any("Cat Shape" in log for log in logs)


# ── PropertyShapes ────────────────────────────────────────────────────────────

def test_property_shape_with_rdfs_label_passes(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape ; rdfs:label "Has Fur Shape" .
    """)
    assert run_qa(g).get("PropertyShape without label").passed


def test_property_shape_without_label_fails(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape .
    """)
    check = run_qa(g).get("PropertyShape without label")
    assert not check.passed
    assert check.count == 1

def test_property_shape_with_rdfs_label_verbose_is_printed(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape ; rdfs:label "Has Fur Shape" .
    """)
    logs = run_qa(g, verbose=True).logs
    assert any("Has Fur Shape" in log for log in logs)
