from scripts.ontology_qa import run_qa


# ── Classes ───────────────────────────────────────────────────────────────────

def test_class_with_rdfs_comment_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:comment "The class of all cats." .
    """)
    assert run_qa(g).get("Class without description").passed


def test_class_with_skos_definition_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; skos:definition "A domestic feline." .
    """)
    assert run_qa(g).get("Class without description").passed


def test_class_with_dcterms_description_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; dcterms:description "A domestic feline." .
    """)
    assert run_qa(g).get("Class without description").passed


def test_class_without_description_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    """)
    check = run_qa(g).get("Class without description")
    assert not check.passed
    assert check.count == 1
    assert "Cat" in check.elements


def test_one_of_two_classes_missing_description_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class ; rdfs:comment "A cat." .
    :Dog a owl:Class .
    """)
    check = run_qa(g).get("Class without description")
    assert not check.passed
    assert check.count == 1


# ── Properties ────────────────────────────────────────────────────────────────

def test_property_with_rdfs_comment_passes(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:comment "Connects to fur." .
    """)
    assert run_qa(g).get("Property without description").passed


def test_property_without_description_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty .
    """)
    check = run_qa(g).get("Property without description")
    assert not check.passed
    assert check.count == 1
    assert "hasFur" in check.elements


# ── NodeShapes ────────────────────────────────────────────────────────────────

def test_node_shape_with_rdfs_comment_passes(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; rdfs:comment "Validates cat entities." .
    """)
    assert run_qa(g).get("NodeShape without description").passed


def test_node_shape_without_description_fails(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape .
    """)
    check = run_qa(g).get("NodeShape without description")
    assert not check.passed
    assert check.count == 1


# ── PropertyShapes ────────────────────────────────────────────────────────────

def test_property_shape_with_rdfs_comment_passes(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape ; rdfs:comment "Validates fur property." .
    """)
    assert run_qa(g).get("PropertyShape without description").passed


def test_property_shape_without_description_fails(make_graph):
    g = make_graph("""
    :hasFurShape a sh:PropertyShape .
    """)
    check = run_qa(g).get("PropertyShape without description")
    assert not check.passed
    assert check.count == 1
