from scripts.ontology_qa import profiling, print_profiling_metrics, exclude_instance_data


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
    g = make_graph(": a owl:Ontology .")
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
    g = make_graph(": a owl:Ontology .")
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


def test_ontology_imports(make_graph):
    g = make_graph("""
    : a owl:Ontology ;
    rdfs:label "Animal Ontology" ;
    owl:imports <http://example.org/>, <http://my.ont.example#> .
    """)
    metrics, _ = profiling(g)
    assert metrics['imports'] == 2


def test_ontology_depth_linear(make_graph):
    g = make_graph("""
    :Animal a rdfs:Class .
    :Cat a rdfs:Class ;
    rdfs:subClassOf :Animal .
    :Siamese a rdfs:Class ;
    rdfs:subClassOf :Cat .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['HierarchyDepth']) == 2

def test_ontology_depth_multiple_inheritance(make_graph):
    g = make_graph("""
    :Animal a rdfs:Class .
    :Cat a rdfs:Class ;
    rdfs:subClassOf :Animal .
    :Pet a rdfs:Class ;
    rdfs:subClassOf :Animal .
    :Siamese a rdfs:Class ;
    rdfs:subClassOf :Cat, :Pet .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['HierarchyDepth']) == 2

def test_ontology_depth_non_dag(make_graph):
    g = make_graph("""
    :A a owl:Class ; rdfs:subClassOf :B .
    :B a owl:Class ; rdfs:subClassOf :A .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['HierarchyDepth']) == -1

def test_average_branching_factor(make_graph):
    g = make_graph("""
    :Animal a rdfs:Class .
    :Cat a rdfs:Class ;
    rdfs:subClassOf :Animal .
    :Siamese a rdfs:Class ;
    rdfs:subClassOf :Cat .
    :Tabby a rdfs:Class ;
    rdfs:subClassOf :Cat .
    """)
    metrics, _ = profiling(g)
    assert float(metrics['aveBranchFactor']) == 1.5

# Examples from https://protegeproject.github.io/protege/class-expression-syntax/
def test_cardinality_restrictions_some(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :hasPet a owl:ObjectProperty .
    :DogOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:someValuesFrom :Dog
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1


def test_cardinality_restriction_value(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :Tibbs a :Dog .
    :hasPet a owl:ObjectProperty .
    :TibbsOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:hasValue :Tibbs
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1


def test_cardinality_restriction_only(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :hasPet a owl:ObjectProperty .
    :DogOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:allValuesFrom :Dog
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1


def test_cardinality_restriction_min(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :hasPet a owl:ObjectProperty .
    :DogOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:minQualifiedCardinality 1 ;
        owl:onClass :Dog
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1


def test_cardinality_restriction_max(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :hasPet a owl:ObjectProperty .
    :ModestDogOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:maxQualifiedCardinality 2 ;
        owl:onClass :Dog
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1


def test_cardinality_restriction_exactly(make_graph):
    g = make_graph("""
    :Dog a rdfs:Class .
    :hasPet a owl:ObjectProperty .
    :MassiveDogOwner a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :hasPet ;
        owl:qualifiedCardinality 20 ;
        owl:onClass :Dog
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1

def test_cardinality_restriction_self(make_graph):
    g = make_graph("""
    :loves a owl:ObjectProperty .
    :NarcissisticPerson a rdfs:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty :loves ;
        owl:hasSelf 1
    ] .
    """)
    metrics, _ = profiling(g)
    assert int(metrics['CardinalityRestrictions']) == 1

def test_profiling_metrics_output(make_graph):
    g = make_graph("""
    :Cat a owl:Class .
    :Dog a owl:Class .
    :hasFur a owl:ObjectProperty .
    :hasAge a owl:DatatypeProperty .
    """)
    metrics = {'filesProcessed': 0, 'triples': len(g), 'instances': 0}
    p_metrics, violations = profiling(g)
    metrics.update(p_metrics)
    output = print_profiling_metrics(metrics, violations, True)
    assert "RDF/OWL classes: 2" in output
    assert "RDF/OWL properties: 2" in output
    assert "Instance data: 0" in output
    assert "SHACL Node Shapes: 0" in output
    assert "SHACL Property Shapes: 0" in output

def test_instance_data(make_graph):
    g = make_graph("""
    :Dog a owl:Class .
    :fuffy a :Dog; rdfs:label "Fuffy" .
    """)
    initial_size = len(g)
    exclusion_triples, instances = exclude_instance_data(g)
    g -= exclusion_triples
    assert initial_size > len(g)
    assert instances == 1
