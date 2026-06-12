from scripts.ontology_qa import run_qa


# ── Isolated Classes ──────────────────────────────────────────────────────────

def test_class_connected_via_subclass_passes(make_graph):
    g = make_graph("""
    :Animal a owl:Class .
    :Cat a owl:Class ; rdfs:subClassOf :Animal .
    """)
    assert run_qa(g).get("Isolated classes").passed


def test_class_connected_via_domain_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :hasCat a owl:ObjectProperty ; rdfs:domain :Cat .
    """)
    assert run_qa(g).get("Isolated classes").passed


def test_class_connected_via_sh_target_class_passes(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :CatShape a sh:NodeShape ; sh:targetClass :Cat .
    """)
    assert run_qa(g).get("Isolated classes").passed


def test_isolated_class_fails(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :Dog a owl:Class .
    :Animal a owl:Class .
    :Cat rdfs:subClassOf :Animal .
    :Dog rdfs:subClassOf :Animal .
    :Claw a owl:Class .
    """)
    check = run_qa(g).get("Isolated classes")
    assert not check.passed
    assert "Claw" in check.elements


# ── Domain and Range ──────────────────────────────────────────────────────────

def test_property_with_domain_and_range_passes(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ;
        rdfs:domain :Cat ;
        rdfs:range :Fur .
    """)
    check_d = run_qa(g).get("Property without domain")
    check_r = run_qa(g).get("Property without range")
    assert check_d.passed
    assert check_r.passed


def test_property_missing_domain_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:range :Fur .
    """)
    result = run_qa(g)
    assert not result.get("Property without domain").passed
    assert result.get("Property without range").passed
    assert "hasFur" in result.get("Property without domain").elements


def test_property_missing_range_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:domain :Cat .
    """)
    result = run_qa(g)
    assert result.get("Property without domain").passed
    assert not result.get("Property without range").passed
    assert "hasFur" in result.get("Property without range").elements


def test_property_missing_both_domain_and_range_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty .
    """)
    result = run_qa(g)
    assert not result.get("Property without domain").passed
    assert not result.get("Property without range").passed


# ── Non-Unique Identifiers ────────────────────────────────────────────────────

def test_unique_identifiers_pass(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :hasFur a owl:ObjectProperty .
    """)
    assert run_qa(g).get("Non-unique identifiers").passed


def test_same_iri_as_class_and_property_fails(make_graph):
    g = make_graph("""
    :hasFur a owl:Class .
    :hasFur a owl:ObjectProperty .
    """)
    check = run_qa(g).get("Non-unique identifiers")
    assert not check.passed
    assert check.count == 1
    assert "hasFur" in check.elements


# ── Subclass Cycles ───────────────────────────────────────────────────────────

def test_no_subclass_cycle_passes(make_graph):
    g = make_graph("""
    :Animal a owl:Class .
    :Cat a owl:Class ; rdfs:subClassOf :Animal .
    """)
    assert run_qa(g).get("Subclass Cycles").passed


def test_direct_subclass_cycle_fails(make_graph):
    g = make_graph("""
    :A a owl:Class ; rdfs:subClassOf :B .
    :B a owl:Class ; rdfs:subClassOf :A .
    """)
    check = run_qa(g).get("Subclass Cycles")
    assert not check.passed
    assert check.count == 2
    assert "A" in check.elements
    assert "B" in check.elements


def test_three_class_cycle_fails(make_graph):
    g = make_graph("""
    :A a owl:Class ; rdfs:subClassOf :B .
    :B a owl:Class ; rdfs:subClassOf :C .
    :C a owl:Class ; rdfs:subClassOf :A .
    """)
    check = run_qa(g).get("Subclass Cycles")
    assert not check.passed
    assert check.count == 3


# ── Untyped Classes ───────────────────────────────────────────────────────────

def test_typed_class_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Fur a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :Fur .
    """)
    assert run_qa(g).get("Untyped Classes").passed


def test_class_used_as_range_without_declaration_fails(make_graph):
    # :UndeclaredClass is used as a range but never declared as owl:Class/rdfs:Class.
    # The check only fires for classes in the ontology's own namespace, and requires at
    # least one declared class so the guard condition (classCount > 0) doesn't short-circuit.
    g = make_graph("""
    : a owl:Ontology .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :UndeclaredClass .
    """)
    check = run_qa(g).get("Untyped Classes")
    assert not check.passed
    assert "UndeclaredClass" in check.elements


def test_untyped_class_check_requires_ontology_declaration(make_graph):
    # Without owl:Ontology, the namespace filter can't fire; no violations reported.
    g = make_graph("""
    :hasFur a owl:ObjectProperty ; rdfs:range :UndeclaredClass .
    """)
    assert run_qa(g).get("Untyped Classes").passed


# ── Untyped Properties ────────────────────────────────────────────────────────

def test_property_used_without_declaration_fails(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Fuffy :hasClaws :someClaw .
    """)
    check = run_qa(g).get("Untyped Properties")
    assert not check.passed


def test_declared_property_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :hasClaws a owl:ObjectProperty .
    :Fuffy :hasClaws :someClaw .
    """)
    assert run_qa(g).get("Untyped Properties").passed


# ── Namespace Hijacking ───────────────────────────────────────────────────────

def test_no_hijacking_passes(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Cat a owl:Class .
    """)
    assert run_qa(g).get("Namespace hijacking").passed


def test_external_prefix_used_as_subject_fails(make_graph):
    # skos:Creature is defined in the skos namespace, not the ontology namespace —
    # creating it here is namespace hijacking.
    g = make_graph("""
    : a owl:Ontology .
    skos:Creature a rdfs:Class .
    """)
    check = run_qa(g).get("Namespace hijacking")
    assert not check.passed
    assert "Creature" in check.elements
