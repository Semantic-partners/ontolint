#!/usr/bin/env python3
# Ontology Quality Assessment Script (v0.1)
# SEMANTIC PARTNERS LTD, 2025
# Authors: Simon Shapiro, Otello M Roscioni.
# Last revision: 2025-09-16

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""
import rdflib
from rdflib import Graph, URIRef
import argparse
from urllib.parse import urlparse

# SPARQL queries

subclass_inference_rule = """
CONSTRUCT {
    ?this rdf:type ?superClass .
}
WHERE {
    {
        SELECT ?this ?superClass WHERE {
            ?this rdf:type ?subClass .
            ?subClass rdfs:subClassOf ?superClass .
        }
    }
    FILTER NOT EXISTS {
        ?this rdf:type ?superClass .
    }
}
"""

# Domain or Range violations.
validation_query = """
SELECT ?s ?p ?o ?domain ?range WHERE {
    ?s ?p ?o .

    OPTIONAL { ?p rdfs:domain ?domain . }
    OPTIONAL { ?p rdfs:range ?range . }

    FILTER (
      (BOUND(?domain) && NOT EXISTS {
        ?s a ?stype .
        ?stype rdfs:subClassOf* ?domain .
      })
      ||
      (isIRI(?o) && BOUND(?range) && NOT EXISTS {
        ?o a ?otype .
        ?otype rdfs:subClassOf* ?range .
      })
    )
}
"""

# IA3 Hierarchy Overspecialisation
# Leaf classes with no instances
ia3_leaf_classes = """
SELECT ?c WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  FILTER NOT EXISTS {
    ?sub rdfs:subClassOf ?c .
    ?instance rdf:type ?c .
  }
}
"""

# Number of Deprecated Classes and Properties
# Count elements marked as deprecated
deprecated_class = """
SELECT DISTINCT ?c
WHERE {
  ?c a owl:DeprecatedClass .
}
"""
deprecated_property = """
SELECT DISTINCT ?p
WHERE {
  ?p a owl:DeprecatedProperty .
}
"""

# IC1 Number of Isolated Elements
# Classes declared but never used in any triple
isolated_classes = """
SELECT DISTINCT ?c
WHERE {  
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  FILTER NOT EXISTS {
    ?s rdfs:subClassOf|rdfs:domain|rdfs:range ?o .
    FILTER(?c IN (?s, ?o))
  }
}
"""

# IC2 Missing Domain or Range in Properties
# Properties without any rdfs:domain or rdfs:range declaration
ic2_missing_dr_property = """
SELECT DISTINCT ?p ?domain ?range
WHERE {
  VALUES ?type { owl:ObjectProperty rdf:Property }
  ?p a ?type .
  OPTIONAL { ?p rdfs:domain ?domain }
  OPTIONAL { ?p rdfs:range  ?range  }
  FILTER( !BOUND(?domain) || !BOUND(?range) )
}
"""

# (IO1 Number of Polysemous Elements)
# Non-unique identifiers
# Same IRI used for classes and/or properties
io1_polysemous = """
SELECT ?iri
  (GROUP_CONCAT(DISTINCT REPLACE(STR(?type), ".*/", ""); separator=", ") AS ?declaredAs)
WHERE {
  VALUES ?type { owl:Class rdfs:Class owl:ObjectProperty rdf:Property owl:ObjectProperty owl:DatatypeProperty  owl:AnnotationProperty }
  ?iri a ?type .
}
GROUP BY ?iri
HAVING (COUNT(DISTINCT ?type) > 1)
"""

unique_identifiers = """
SELECT ?iri
  (GROUP_CONCAT(DISTINCT REPLACE(STR(?type), ".*/", ""); separator=", ") AS ?declaredAs)
WHERE {
  VALUES ?type { owl:Class rdfs:Class owl:ObjectProperty rdf:Property owl:ObjectProperty owl:DatatypeProperty  owl:AnnotationProperty }
  ?iri a ?type .
  FILTER(
    !(
      ?type = rdfs:Class &&
      EXISTS { ?iri a owl:Class }
    )
  )
  FILTER(
    !(
      ?type = rdf:Property &&
      EXISTS { ?iri a owl:ObjectProperty }
    )
  )
}
GROUP BY ?iri
HAVING (COUNT(DISTINCT ?type) > 1)
"""

# IO2 Including Cycles in a Class Hierarchy
# Detect classes involved in subclass cycles
io2_cycles = """
SELECT DISTINCT ?c WHERE {
  ?c rdfs:subClassOf+ ?c .
}
"""

# IO3 Missing Disjointness
# Sibling classes under the same direct superclass that are not declared disjoint.
# Is it really a quality metric?
io3_missing_disjoints = """
SELECT DISTINCT ?c1 ?c2 WHERE {
  ?c1 rdfs:subClassOf ?parent .
  ?c2 rdfs:subClassOf ?parent .
  FILTER(?c1 != ?c2)
  FILTER NOT EXISTS { ?c1 owl:disjointWith ?c2 }
}
"""

# IO4 Defining Multiple Domains/Ranges
# Properties declared with more than one domain or more than one range
io4_multiple_dr = """
SELECT ?p (COUNT(DISTINCT ?d) AS ?domainCount) (COUNT(DISTINCT ?r) AS ?rangeCount)
WHERE {
  VALUES ?type { owl:ObjectProperty rdf:Property }
  ?p a ?type .
  OPTIONAL { ?p rdfs:domain ?d }
  OPTIONAL { ?p rdfs:range  ?r }
  FILTER( BOUND(?d) && BOUND(?r) )
}
GROUP BY ?p
HAVING (?domainCount > 1 || ?rangeCount > 1)
"""

# IO5 Property Chain with One Property
# owl:propertyChainAxiom lists with exactly one member
io5_wrong_property_chain = """
SELECT ?p WHERE {
  ?p owl:propertyChainAxiom ?list .
  ?list rdf:first ?singleMember .
  ?list rdf:rest  rdf:nil .
}
"""

# IO7 Tangledness
# List classes having more than one direct rdfs:subClassOf parent
io7_tangledness = """
SELECT ?c (COUNT(?parent) AS ?directAncestors)
WHERE {
  ?c rdfs:subClassOf ?parent .
}
GROUP BY ?c
HAVING (COUNT(?parent) > 1)
"""

# ISM1 No OWL ontology declaration
ism1_no_owl_declaration = """
SELECT ?ont
WHERE {
  ?ont a owl:Ontology .
}
"""

# No ontology Description
no_ont_description = """
SELECT ?ont
WHERE {
  ?ont a owl:Ontology .
  FILTER NOT EXISTS {
    ?ont rdfs:comment|dcterms:abstract|dcterms:description|skos:definition|skos:note ?a .
  }
}
"""

# ISU1 Missing Annotations
# Classes or properties lacking rdfs:label or rdfs:comment
isu1_missing_annotations = """
SELECT DISTINCT ?c ?p
WHERE {
  {
    ?c a ?type .
    FILTER( ?type IN (
        owl:Class,
        rdfs:Class
    ))
    FILTER (
      NOT EXISTS { ?c rdfs:label   ?lbl   }
      ||
      NOT EXISTS { ?c rdfs:comment ?cmt   }
    )
  }
  UNION
  {
    ?p a ?ptype .
    FILTER( ?ptype IN (
          rdf:Property,
          owl:ObjectProperty
    ))
    FILTER (
      NOT EXISTS { ?p rdfs:label   ?lbl2  }
      ||
      NOT EXISTS { ?p rdfs:comment ?cmt2  }
    )
  }
}
"""

class_missing_label = """
SELECT DISTINCT ?c
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  FILTER NOT EXISTS { ?c rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl }
}
"""

property_missing_label = """
SELECT DISTINCT ?p
WHERE {
  VALUES ?type { owl:ObjectProperty rdf:Property }
  ?p a ?type .
  FILTER NOT EXISTS { ?p rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl }
}
"""

class_missing_comment = """
SELECT DISTINCT ?c
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  FILTER NOT EXISTS { ?c rdfs:comment|dcterms:description|skos:definition ?lbl }
}
"""

property_missing_comment = """
SELECT DISTINCT ?p
WHERE {
  VALUES ?type { owl:ObjectProperty rdf:Property }
  ?p a ?type .
  FILTER NOT EXISTS { ?p rdfs:comment|dcterms:description|skos:definition ?lbl }
}
"""

# Count the classes and properties in the current graph.
# To avoid unbound ?p when evaluating ?c (and vice versa), 
# two independent sub-SELECT blocks are specified, that both fire in the same solution.
# UNION is not used as it gives two rows.
count_cp = """
SELECT  ?classCount ?propertyCount
WHERE {
 {
   SELECT (COUNT(DISTINCT ?c) AS ?classCount)
   WHERE {
    VALUES ?type { owl:Class rdfs:Class }
    ?c a ?type .
   }
 }
 {
   SELECT (COUNT(DISTINCT ?p) AS ?propertyCount)
   WHERE {
    VALUES ?type { owl:ObjectProperty rdf:Property }
    ?p a ?type .
   }
 }
}
"""

# Average Class Connectivity
# Note that this query misses the classes that are completely isolated (no links at all).
class_connectivity = """
SELECT (AVG(?connectivity) AS ?averageConnectivity)
WHERE {
  {
    SELECT ?class (COUNT(DISTINCT ?link) AS ?connectivity)
    WHERE {
      VALUES ?type { owl:Class rdfs:Class }
      ?c a ?type .
      {
        # subclass and superclass relationships
        { ?class rdfs:subClassOf ?link }
        UNION
        { ?link rdfs:subClassOf ?class }
        # object property domain/range usage
        UNION
        { 
          VALUES ?ptype { owl:ObjectProperty rdf:Property }
          ?p a ?ptype .
          ?prop rdfs:domain|rdfs:range ?class .
          BIND(?prop AS ?link)
        }
      }
    }
    GROUP BY ?class
  }
}
"""

# Classes with the same label
class_same_label = """
SELECT ?label (GROUP_CONCAT(DISTINCT ?class; separator=", ") AS ?classes)
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?class a ?type .
  ?class rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?label .
}
GROUP BY ?label
HAVING (COUNT(DISTINCT ?class) > 1)
"""

# Properties with the same label
property_same_label = """
SELECT ?label (GROUP_CONCAT(DISTINCT ?p; separator=", ") AS ?properties)
WHERE {
  VALUES ?type { owl:ObjectProperty rdf:Property }
  ?p a ?type .
  ?p rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?label .
}
GROUP BY ?label
HAVING (COUNT(DISTINCT ?p) > 1)
"""

# Untyped class
# Class without rdf:type owl:Class or rdfs:Class declaration
untyped_class = """
SELECT DISTINCT ?c
WHERE {
   { ?s rdf:type ?c . }
   UNION
   { ?s rdfs:domain ?c . }
   UNION
   { ?s rdfs:range ?c . }
  # Exclude built-in vocabulary
  FILTER (
    !regex(STR(?c), "^http://www.w3.org/2002/07/owl#") &&
    !regex(STR(?c), "^http://www.w3.org/2000/01/rdf-schema#") &&
    !regex(STR(?c), "^http://www.w3.org/1999/02/22-rdf-syntax-ns#")
  )
  # Exclude classes that are explicitly typed as owl:Class or rdfs:Class
  FILTER ( NOT EXISTS { ?c rdf:type owl:Class . } && NOT EXISTS { ?c rdf:type rdfs:Class . } )
}
"""

# Untyped property
# Property without rdf:type rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration
untyped_property = """
SELECT DISTINCT ?p
WHERE {
  # Find resources used as predicates
  ?s ?p ?o .

  # Exclude built-in vocabulary
  FILTER (
    !regex(STR(?p), "^http://www.w3.org/2002/07/owl#") &&
    !regex(STR(?p), "^http://www.w3.org/2000/01/rdf-schema#") &&
    !regex(STR(?p), "^http://www.w3.org/1999/02/22-rdf-syntax-ns#") &&
    !regex(STR(?p), "^http://www.w3.org/2004/02/skos/core#") &&
    !regex(STR(?p), "^http://www.w3.org/2001/XMLSchema#") &&
    !regex(STR(?p), "^http://purl.org/dc/terms#")
  )

  # Exclude properties that are explicitly typed
  FILTER (
    NOT EXISTS { ?p rdf:type rdf:Property } &&
    NOT EXISTS { ?p rdf:type owl:ObjectProperty } &&
    NOT EXISTS { ?p rdf:type owl:DatatypeProperty }
  )
}
"""

# Filter resources from external vocabularies.
# The result is a URI that has to be checked to points to a valid resource on the web.
external_resource = """
SELECT DISTINCT ?resource
WHERE {
  # Resources declared as class
  {
    VALUES ?type { owl:Class rdfs:Class }
    ?resource a ?type .
  }
  UNION
  # Resources used as predicate
  {
    ?s ?resource ?o .
  }
  UNION
  # Resources used as object
  {
    ?s2 ?p ?resource .
  }
  # Detect if the class URI starts with a known external namespace
  FILTER (
    regex(STR(?resource), "^http://www.w3.org/1999/02/22-rdf-syntax-ns#") ||
    regex(STR(?resource), "^http://www.w3.org/2000/01/rdf-schema#") ||
    regex(STR(?resource), "^http://www.w3.org/2002/07/owl#") ||
    regex(STR(?resource), "^http://www.w3.org/2004/02/skos/core") ||
    regex(STR(?resource), "^http://www.w3.org/XML/1998/namespace") ||
    regex(STR(?resource), "^http://purl.org/dc/elements/1.1/") ||
    regex(STR(?resource), "^http://purl.org/dc/terms/") ||
    regex(STR(?resource), "^http://purl.org/vocab/vann/") ||
    regex(STR(?resource), "^http://xmlns.com/foaf/0.1/")
  )
}
"""

# Namespace hijacking
# Define a class in the namespace using an external vocabulary prefix.
hijacking = """
SELECT DISTINCT ?resource
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?resource a ?type .
  # Detect if the class URI starts with a known external namespace
  FILTER (
    regex(STR(?resource), "^http://www.w3.org/1999/02/22-rdf-syntax-ns#") ||
    regex(STR(?resource), "^http://www.w3.org/2000/01/rdf-schema#") ||
    regex(STR(?resource), "^http://www.w3.org/2002/07/owl#") ||
    regex(STR(?resource), "^http://www.w3.org/2004/02/skos/core") ||
    regex(STR(?resource), "^http://www.w3.org/XML/1998/namespace") ||
    regex(STR(?resource), "^http://purl.org/dc/elements/1.1/") ||
    regex(STR(?resource), "^http://purl.org/dc/terms/") ||
    regex(STR(?resource), "^http://purl.org/vocab/vann/") ||
    regex(STR(?resource), "^http://xmlns.com/foaf/0.1/")
  )
}
"""

def get_namespace(uri):
    """Extract namespace from a URIRef."""
    if '#' in uri:
        return uri.rsplit('#', 1)[0] + '#'
    elif '/' in uri:
        return uri.rsplit('/', 1)[0] + '/'
    return uri  # fallback

def prefixes(g):
    # Create a dictionary for the declared prefixes
    declared_prefixes = {}
    for prefix, uri in g.namespace_manager.namespaces():
        uri_str = str(uri)
        declared_prefixes[uri_str] = prefix

    # Collect all namespaces actually used in the graph
    used_namespaces = set()
    for s, p, o in g:
        for term in [s, p, o]:
            if isinstance(term, URIRef):
                ns = get_namespace(str(term))
                used_namespaces.add(ns)

    # Filter the declared prefixes into those that are actually used
    used_prefixes = {}
    for ns in used_namespaces:
        if ns in declared_prefixes:
            prefix = declared_prefixes[ns]
            if len(prefix) > 0: used_prefixes[prefix] = ns

    return used_prefixes

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data_files', nargs='+', help='List of RDF files to process.')
    args = parser.parse_args()

    # 1. Load Data
    g = rdflib.Graph()
    for f in args.data_files:
        print(f"Loading data from: {f}")
        # Try to guess format from file extension
        if f.lower().endswith(('.ttl', '.turtle')):
            fmt = "turtle"
        elif f.lower().endswith(('.rdf', '.owl', '.xml')):
            fmt = "xml"
        else:
            fmt = None  # Let rdflib try to guess
        try:
            g.parse(f, format=fmt)
        except Exception as e:
            print(f"Failed to parse {f} ({fmt if fmt else 'auto'}): {e}")
            continue
    
    # Create an empty dictionary to store the metrics for the ontology.
    qa_metrics = {}
    qa_metrics['triples']= len(g)
    print(f"Initial graph size: {qa_metrics['triples']} triples")

    # Count initial classes and properties
    results = g.query(count_cp)
    if not results:
        print("ERROR - No classes or properties found.")
        return
    else:
        (row,) = results
        print(f"Found {row.classCount} classes and {row.propertyCount} properties.")
        qa_metrics['classCount']= row.classCount
        qa_metrics['propertyCount'] = row.propertyCount
        
    print("-" * 20)

    # List all used prefixes
    active_prefixes = prefixes(g)
    qa_metrics['vocabulariesUsed'] = len(active_prefixes)
    print(f"External vocabularies declared: {qa_metrics['vocabulariesUsed']}")
    for pfx, ns in active_prefixes.items():
        print(f" - {pfx}: {ns}")

    # 2. Simulate Inference
    print("\nApplying Subclass inference rule iteratively...")
    while True:
        inferred_triples_result = g.query(subclass_inference_rule)
        if not inferred_triples_result:
            print("No new subclass inferences to add. Inference complete.")
            break

        graph_size_before = len(g)
        for t in inferred_triples_result:
            g.add(t)
        graph_size_after = len(g)

        if graph_size_after == graph_size_before:
            print("No new subclass inferences in this pass. Inference complete.")
            break
        else:
            print(f"Added {graph_size_after - graph_size_before} new triples. Continuing inference...")

    print(f"Final graph size after inference: {len(g)} triples")

    # ISM1 No OWL ontology declaration
    print("\nRunning check 1: OWL ontology declaration.")
    results = g.query(ism1_no_owl_declaration)
    print("")
    if not results:
        print(f"VIOLATION - No owl:Ontology declaration found.")
        qa_metrics['ontologyDeclared'] = 0
    elif len(results) == 1:
        (row,) = results
        print(f"PASS - Found 1 ontology with owl:Ontology declaration:\n - {row.ont}")
        qa_metrics['ontologyDeclared'] = row.ont
    elif len(results) > 1:
        print(f"WARNING - Found {len(results)} owl:Ontology declarations:")
        for row in results:
            print(f" - {row.ont}")
            qa_metrics['ontologyDeclared'] += " {row.ont}"
    
    print("-" * 20)

    # Missing ontology description.
    if len(results) > 0:
        print("\nRunning check 2: Ontology description.")
        results = g.query(no_ont_description)
        print("") 
        if not results:
            print("PASS - All ontologies have a description.")
            qa_metrics['ontologyDescription'] = 0 
        else:
            qa_metrics['ontologyDescription'] = len(results)
            print(f"VIOLATION - Found {qa_metrics['ontologyDescription']} ontologies without any description:")
            for row in results:
                print(f" - {row.ont}")
    else:
        print("\nSkipping check 2: Ontology description (no ontology declared).")
        qa_metrics['ontologyDescription'] = 0 
    
    print("-" * 20)

    # Missing Annotations
    print("\nRunning check 3: Classes missing label annotations.")
    results = g.query(class_missing_label)
    print("-" * 20)
    
    if not results:
        print("PASS - All classes have a label annotation.")
        qa_metrics['missingClassLabel'] = 0
    else:
        qa_metrics['missingClassLabel'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingClassLabel']} classes missing a label annotation:")
        for c in results:
          print(f" - {c[0]}")

    print("-" * 20)

    print("\nRunning check 4: Properties missing label annotations.")
    results = g.query(property_missing_label)
    print("-" * 20)

    if not results:
        print("PASS - All properties have a label annotation.")
        qa_metrics['missingPropertyLabel'] = 0
    else:
        qa_metrics['missingPropertyLabel'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingPropertyLabel']} properties missing a label annotation.")
        for p in results:
          print(f" - {p[0]}")
    
    print("-" * 20)

    print("\nRunning check 5: Classes missing description annotation.")  
    results = g.query(class_missing_comment)
    print("-" * 20)
    
    if not results:
        print("PASS - All classes have a description annotation.")
        qa_metrics['missingClassDescription'] = 0
    else:
        qa_metrics['missingClassDescription'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingClassDescription']} classes missing a description annotation:")
        for c in results:
          print(f" - {c[0]}")

    print("-" * 20)

    print("\nRunning check 6: Properties missing description annotations.")
    results = g.query(property_missing_comment)
    print("-" * 20)

    if not results:
        print("PASS - All properties have a description annotation.")
        qa_metrics['missingPropertyDescription'] = 0
    else:
        qa_metrics['missingPropertyDescription'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingPropertyDescription']} properties missing a description annotation.")
        for p in results:
          print(f" - {p[0]}")
    
    print("-" * 20)

    print("\nRunning check 7: Classes with the same label.")
    results = g.query(class_same_label)
    print("-" * 20)
    if not results:
        print("PASS - No classes share the same label.")
        qa_metrics['nonUniqueClassLabels'] = 0
    else:
        qa_metrics['nonUniqueClassLabels'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['nonUniqueClassLabels']} labels shared by multiple classes.")
        print(f"- Label\t\tClasses")
        for row in results:
            print(f" - \"{row.label}\"\t{row.classes}")
    
    print("-" * 20)

    print("\nRunning check 8: Properties with the same label.")
    results = g.query(property_same_label)
    print("-" * 20)
    if not results:
        print("PASS - No property share the same label.")
        qa_metrics['nonUniquePropertyLabels'] = 0
    else:
        qa_metrics['nonUniquePropertyLabels'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['nonUniquePropertyLabels']} labels shared by multiple properties.")
        print(f"- Label\t\tProperties")
        for row in results:
            print(f" - \"{row.label}\"\t{row.properties}")
    
    print("-" * 20)

    # Number of Isolated Classes
    print("\nRunning check 9: Number of isolated classes.")
    results = g.query(isolated_classes)
    print("-" * 20)

    if not results:
        print("PASS - All classes are connected to another class through a subclass or property relation.")
        qa_metrics['isolatedClasses'] = 0
    else:
        qa_metrics['isolatedClasses'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['isolatedClasses']} isolated classes:")
        for row in results:
          print(f" - {row[0]}")
            
    print("-" * 20)

    # Missing Domain or Range in Properties
    print("\nRunning check 10: Missing Domain or Range in Properties:")
    results = g.query(ic2_missing_dr_property)
    print("-" * 20)
    if not results:
        print("PASS - All properties have domain and range defined.")
        qa_metrics['missingDomainRange'] = 0
    else:
        qa_metrics['missingDomainRange'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingDomainRange']} properties without rdfs:domain or rdfs:range declaration:")
        print(f"Property","Domain","Range",sep="\t")
        for row in results:
            print(f"{row.p}","\t",f"{row.domain if row.domain else 'None'}","\t",f"{row.range if row.range else 'None'}",sep="")
            
    print("-" * 20)

    # Non-unique identifiers
    print("\nRunning check 11: Non-unique identifiers.")
    results = g.query(unique_identifiers)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['nonUniqueIdentifiers'] = 0
    else:
        qa_metrics['nonUniqueIdentifiers'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['nonUniqueIdentifiers']} elements with non-unique identifiers:")
        for row in results:
            print(f"IRI: {row.iri} - Declared as: {row.declaredAs}")
    
    print("-" * 20)

    # IO2 Including Cycles in a Class Hierarchy
    print("\nRunning check 12: Including Cycles in a Class Hierarchy")
    results = g.query(io2_cycles)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['subclassCycles'] = 0
    else:
        qa_metrics['subclassCycles'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['subclassCycles']} classes involved in subclass cycles:")
        for row in results:
            print(f" - {row.c}")
    
    print("-" * 20)

    # Untyped class
    print("\nRunning check 13: Untyped class")
    results = g.query(untyped_class)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['untypedClasses'] = 0
    else:
        qa_metrics['untypedClasses'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['untypedClasses']} classes without rdf:type owl:Class or rdfs:Class declaration:")
        for row in results:
            print(f" - {row.c}")
    
    print("-" * 20)

     # Untyped property
    print("\nRunning check 14: Untyped property")
    results = g.query(untyped_property)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['untypedProperties'] = 0
    else:
        qa_metrics['untypedProperties'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['untypedProperties']} property without rdf:Property, owl:ObjectProperty, or owl:DatatypeProperty declaration:")
        for row in results:
            print(f" - {row.p}")
    
    print("-" * 20)

     # Namespace hijacking
    print("\nRunning check 15: Namespace hijacking")
    results = g.query(hijacking)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['hijacking'] = 0
    else:
        qa_metrics['hijacking'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['hijacking']} resources defined using an external vocabulary prefix:")
        for row in results:
            print(f" - {row.resource}")
    
    print("-" * 20)

    # Remaining profiling metrics.

    # Number of Deprecated Classes and Properties
    print("\nRunning check 16: Number of Deprecated Classes")
    results = g.query(deprecated_class)
    print("-" * 20)
    if not results:
      print("PASS - No violations found.")
      qa_metrics['deprecatedClasses'] = 0
    else:
      qa_metrics['deprecatedClasses'] = len(results)
      print(f"VIOLATION - Found {qa_metrics['deprecatedClasses']} deprecated classes:")
      for row in results:
          print(f" - {row.c}")

    print("-" * 20)

    print("\nRunning check 17: Number of Deprecated Properties")
    results = g.query(deprecated_property)
    print("-" * 20)
    if not results:
      print("PASS - No violations found.")
      qa_metrics['deprecatedProperties'] = 0
    else:
      qa_metrics['deprecatedProperties'] = len(results)
      print(f"VIOLATION - Found {qa_metrics['deprecatedProperties']} deprecated properties:")
      for row in results:
          print(f" - {row.p}")

    print("-" * 20)
    ################################################################################
    # Print a summary of the quality metrics in a markdown table.
    print("\nQuality Metrics Summary:")
    # Profiling
    print("| Number of Triples | Class Count | Property Count | Vocabulary Used | Deprecated Classes | Deprecated Properties | ", end="")
    # QA metrics
    print(f"Ontology Declared | Ontology Description | Missing Class Label | Missing Property Label | Missing Class Description | ", end="")
    print(f"Missing Property Description | Non-Unique Class Labels | Non-Unique Property Labels | Isolated Classes | Missing Domain/Range | ", end="")
    print(f"Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Hijacking |")
    print("|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|")
    print(f"| {qa_metrics['triples']} | {qa_metrics['classCount']} | {qa_metrics['propertyCount']} | {qa_metrics['vocabulariesUsed']} | {qa_metrics['deprecatedClasses']} | {qa_metrics['deprecatedProperties']} | ", end="")
    print(f"{qa_metrics['ontologyDeclared']} | {qa_metrics['ontologyDescription']} | {qa_metrics['missingClassLabel']} | {qa_metrics['missingPropertyLabel']} | ", end="")
    print(f"{qa_metrics['missingClassDescription']} | {qa_metrics['missingPropertyDescription']} | {qa_metrics['nonUniqueClassLabels']} | ", end="")
    print(f"{qa_metrics['nonUniquePropertyLabels']} | {qa_metrics['isolatedClasses']} | {qa_metrics['missingDomainRange']} | ", end="")
    print(f"{qa_metrics['nonUniqueIdentifiers']} | {qa_metrics['subclassCycles']} | {qa_metrics['untypedClasses']} | {qa_metrics['untypedProperties']} | {qa_metrics['hijacking']} |")


    # Domain or Range violations (From original Simon's script)
    #print("\nRunning validation query to find violations...")
    #results = g.query(validation_query)
    #print("-" * 20)
    #if not results:
    #    print("No Domain or Range violations found.")
    #else:
    #    print(f"Found {len(results)} Domain or Range violations:")
    #    for row in results:
    #        print(f"Violation:")
    #        print(f"  - Subject:   {row.s}")
    #        print(f"  - Predicate: {row.p}")
    #        print(f"  - Object:    {row.o}")
    #        if row.domain:
    #            print(f"  - Expected Subject Type (Domain): {row.domain}")
    #        if row.range:
    #            print(f"  - Expected Object Type (Range):  {row.range}")

    #print("-" * 20)
    
    # IA3 Hierarchy Overspecialisation
    #print("\nRunning check for IA3 Hierarchy Overspecialisation: leaf classes with no instances")
    #results = g.query(ia3_leaf_classes)
    #print("-" * 20)
    #if not results:
    #    print("No IA3 violations found.")
    #else:
    #    print(f"IA3 - Found {len(results)} leaf classes with no instances:")
    #    for row in results:
    #        print(f" - {row.c}")

    #print("-" * 20)

    # IO3 Missing Disjointness
    # print("\nRunning check for IO3 Missing Disjointness:")
    # results = g.query(io3_missing_disjoints)
    # print("-" * 20)
    # if not results:
    #     print("No IO3 violations found.")
    # else:
    #     print(f"IO2 - Found {len(results)} sibling classes that are not declared as disjoint:")
    #     for row in results:
    #         print(f" - {row.c1}, {row.c2}")
    
    # print("-" * 20)

    # IO4 Defining Multiple Domains/Ranges
    # print("\nRunning check for IO4 Defining Multiple Domains/Ranges:")
    # results = g.query(io4_multiple_dr)
    # print("-" * 20)
    # if not results:
    #     print("No IO4 violations found.")
    # else:
    #     print(f"IO4 - Found {len(results)} properties with multiple domains or ranges:")
    #     print(f"Property","#Domains","#Ranges",sep="\t")
    #     for row in results:
    #         print(f"{row.p}","\t",f"{row.domainCount}","\t",f"{row.rangeCount}",sep="")
    
    # print("-" * 20)

    # IO5 Property Chain with One Property
    # print("\nRunning check for IO5 Property Chain with One Property:")
    # results = g.query(io5_wrong_property_chain)
    # print("-" * 20)
    # if not results:
    #     print("No IO5 violations found.")
    # else:
    #     print(f"IO5 - Found {len(results)} properties with owl:propertyChainAxiom listing exactly one member:")
    #     for row in results:
    #         print(f" - {row.p}")
    
    # print("-" * 20)

    # IO7 Tangledness
    # print("\nRunning check for IO7 Tangledness:")
    # results = g.query(io7_tangledness)
    # print("-" * 20)
    # if not results:
    #     print("No IO7 violations found.")
    # else:
    #     print(f"IO7 - Found {len(results)} classes having more than one direct rdfs:subClassOf parent:")
    #     print(f"Class","#DirectAncestors",sep="\t")
    #     for row in results:
    #         print(f"{row.c}","\t",f"{row.directAncestors}",sep="")
    
    # print("-" * 20)


if __name__ == "__main__":
    main()
