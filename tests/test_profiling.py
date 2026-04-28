from scripts.ontology_qa import profiling


def test_class_count(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :Dog a owl:Class .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['classCount']) == 2


def test_rdfs_class_counted(make_graph):
    g = make_graph("""
    :Cat a rdfs:Class .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['classCount']) == 1


def test_property_count(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty .
    :hasAge a owl:DatatypeProperty .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['propertyCount']) == 2


def test_rdf_property_counted(make_graph):
    g = make_graph("""
    :hasFur a rdf:Property .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['propertyCount']) == 1


def test_no_classes_or_properties(make_graph):
    g = make_graph("")
    metrics, _ = profiling(g)
    assert int(metrics['classCount']) == 0
    assert int(metrics['propertyCount']) == 0


def test_node_shape_count(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape .
    :DogShape a sh:NodeShape .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['nodeShapes']) == 2


def test_property_shape_count(make_graph):
    g = make_graph("""
    :hasNameShape a sh:PropertyShape ; sh:path :hasName .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['propertyShapes']) == 1


def test_no_shapes(make_graph):
    g = make_graph("")
    metrics, _ = profiling(g)
    assert int(metrics['nodeShapes']) == 0
    assert int(metrics['propertyShapes']) == 0


def test_deprecated_class_count(make_graph):
    g = make_graph("""
    :OldCat a owl:DeprecatedClass .
    """)
    metrics, _ = profiling(g)
    assert metrics['deprecatedClasses'] == 1


def test_deprecated_property_count(make_graph):
    g = make_graph("""
    :oldHasFur a owl:DeprecatedProperty .
    """)
    metrics, _ = profiling(g)
    assert metrics['deprecatedProperties'] == 1


def test_no_deprecated(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    """)
    metrics, _ = profiling(g)
    assert metrics['deprecatedClasses'] == 0
    assert metrics['deprecatedProperties'] == 0


def test_vocabularies_used_excludes_ontology_namespace(make_graph):
    g = make_graph("""
    : a owl:Ontology .
    :Cat a owl:Class .
    """)
    metrics, _ = profiling(g)
    # owl is external; the ontology's own namespace should not be counted
    assert metrics['vocabulariesUsed'] >= 1


def test_classes_in_node_shapes(make_graph):
    g = make_graph("""
    :CatShape a sh:NodeShape ; sh:targetClass :Cat .
    :Cat a owl:Class .
    """)
    metrics, _ = profiling(g)
    assert metrics['classesInNodeShapes'] == 1


def test_properties_in_property_shapes(make_graph):
    g = make_graph("""
    :hasFur a owl:ObjectProperty .
    :hasFurShape a sh:PropertyShape ; sh:path :hasFur .
    """)
    metrics, _ = profiling(g)
    assert metrics['propertiesInPropertyShapes'] == 1
