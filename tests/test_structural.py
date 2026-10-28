from scripts.ontology_qa import exec_sparql, run_qa


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
    result = run_qa(g)
    assert result.get("Property without domain").passed
    assert result.get("Property without range").passed


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

def test_property_with_domain_and_range_markdown(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty ;
        rdfs:domain :Cat ;
        rdfs:range :Fur .
    """)
    result = run_qa(g)
    assert any("Missing Domain in Properties" in log for log in result.logs)
    assert any("Missing Range in Properties" in log for log in result.logs)


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


def test_untyped_class_without_ontology_declaration_reports_nothing(make_graph):
    """
    With no owl:Ontology, the namespace guard has nothing to compare against (#102).

    It used to pass everything instead of nothing, so the check reported every term the
    file touched — rdf:type and rdfs:label included — and failed the build on a list that
    was almost entirely other people's vocabulary. The cost of reporting nothing is this
    first case: :UndeclaredClass really is undeclared, and is no longer named. There is no
    way to tell it apart from ex:UndeclaredClass below without a namespace to judge by.
    """
    g = make_graph("""
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :UndeclaredClass .
    """)
    check = run_qa(g).get("Untyped Classes")
    assert check.passed
    assert check.count == 0


def test_untyped_class_without_ontology_declaration_ignores_other_vocabularies(make_graph):
    # The false positive the fix is for: ex:UndeclaredClass belongs to someone else.
    g = make_graph("""
    @prefix ex: <http://test.example.org/test#> .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range ex:UndeclaredClass .
    """)
    assert run_qa(g).get("Untyped Classes").passed


def test_untyped_property_without_ontology_declaration_reports_nothing(make_graph):
    # :chases is an untyped predicate, and ex:owns belongs to someone else. With no
    # declared namespace neither can be judged, and both used to be reported.
    g = make_graph("""
    @prefix ex: <http://test.example.org/test#> .
    :Dog :chases :Cat .
    :Dog ex:owns :Bone .
    """)
    check = run_qa(g).get("Untyped Properties")
    assert check.passed
    assert check.count == 0


def test_the_untyped_queries_require_a_declared_namespace(make_graph):
    """
    The guard is in the queries, not only in the checks that report them.

    Each check short-circuits on the declaration before it looks at its results, so a
    query that went back to passing everything would be invisible through run_qa. These
    are the queries other callers would get.
    """
    g = make_graph("""
    @prefix ex: <http://test.example.org/test#> .
    :DeclaredClass a owl:Class .
    :Dog :chases ex:Cat .
    """)
    assert not exec_sparql(g, 'untyped_class')
    assert not exec_sparql(g, 'untyped_property')


def test_untyped_checks_say_the_metric_is_invalid_rather_than_passing(make_graph):
    # Reporting nothing must not read as PASS: nothing was looked at. Each check says so
    # in its own log, so a reader is not told the file is clean on this point.
    g = make_graph(""":DeclaredClass a owl:Class . :Dog :chases :Cat .""")
    logs = run_qa(g).logs
    for word in ("class", "property"):
        expected = (f"WARNING - Ontology namespace undefined, invalid metric. No way to confirm "
                    f"if a {word} is defined in the ontology or an external vocabulary.")
        assert any(expected in log for log in logs), word


def test_untyped_class_pass_class_from_external_ontology(make_graph):
    g = make_graph("""
    @prefix ex: <http://test.example.org/test#> .
    : a owl:Ontology .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range ex:Fur .
    """)
    assert run_qa(g).get("Untyped Classes").passed


def test_untyped_class_with_ontology_short_iri(make_graph):
    g = make_graph("""
    @prefix : <http://test.example.org/long#> .
    <http://test.example.org/long> a owl:Ontology .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :Fur .
    """)
    assert not run_qa(g).get("Untyped Classes").passed


RDF_PROPOSITION_FORM = "http://www.w3.org/1999/02/22-rdf-syntax-ns#PropositionForm"


def test_untyped_class_exclude_types_skips_stand_ins(make_graph):
    # RDF 1.2 → 1.1 downgrades encode triple terms as rdf:PropositionForm stand-ins in the
    # ontology's own namespace; these aren't classes and should not be flagged when excluded.
    g = make_graph("""
    : a owl:Ontology .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :standIn1 .
    :standIn1 a rdf:PropositionForm .
    """)
    assert not run_qa(g).get("Untyped Classes").passed
    assert run_qa(g, exclude_types=[RDF_PROPOSITION_FORM]).get("Untyped Classes").passed


def test_untyped_class_exclude_types_still_reports_real_untyped_class(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :DeclaredClass a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :standIn1 .
    :hasClaw a owl:ObjectProperty ; rdfs:range :UndeclaredClass .
    :standIn1 a rdf:PropositionForm .
    """)
    check = run_qa(g, exclude_types=[RDF_PROPOSITION_FORM]).get("Untyped Classes")
    assert check.count == 1
    assert "UndeclaredClass" in check.elements
    assert "standIn1" not in check.elements


def test_exclude_types_applies_to_other_class_checks(make_graph):
    # A stand-in that is also typed as a class, with no label/comment and no connections.
    g = make_graph("""
    : a owl:Ontology .
    :Dog a owl:Class ; rdfs:label "Dog" ; rdfs:comment "A dog." ; rdfs:subClassOf :Animal .
    :Animal a owl:Class ; rdfs:label "Animal" ; rdfs:comment "An animal." .
    :standIn1 a owl:Class, rdf:PropositionForm .
    """)
    names = ["Class without label", "Class without description", "Isolated classes"]
    baseline = run_qa(g)
    assert all(not baseline.get(n).passed for n in names)
    result = run_qa(g, exclude_types=[RDF_PROPOSITION_FORM])
    for n in names:
        assert result.get(n).passed, n


def test_exclude_types_applies_to_same_label_check(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Dog a owl:Class ; rdfs:label "Dog" .
    :standIn1 a owl:Class, rdf:PropositionForm ; rdfs:label "Dog" .
    """)
    assert not run_qa(g).get("Classes with the same label").passed
    assert run_qa(g, exclude_types=[RDF_PROPOSITION_FORM]).get("Classes with the same label").passed


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
