#!/usr/bin/env python3
# Ontology Quality Assessment Script (v0.1)
# SEMANTIC PARTNERS LTD, 2025
# Authors: Simon Shapiro, Otello M Roscioni.
# Last revision: 2025-11-17

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
import sys
import os
import json
from datetime import datetime

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

# Domain or Range violations of data.
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
# Classes declared but never used in any other triple connecting them to the rest of the ontology.
# TO DO: classes connected through properties defined in the current namespace.
isolated_classes = """
SELECT DISTINCT ?c
WHERE {  
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  FILTER NOT EXISTS {
    ?s rdfs:subClassOf|rdfs:domain|rdfs:range|sh:targetClass|sh:class ?o .
    FILTER(?c IN (?s, ?o))
  }
}
"""

# IC2 Missing Domain or Range in Properties
# Properties without any rdfs:domain or rdfs:range declaration
ic2_missing_dr_property = """
SELECT DISTINCT ?p ?domain ?range
WHERE {
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
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
  VALUES ?type { owl:Class rdfs:Class owl:ObjectProperty rdf:Property owl:DatatypeProperty  owl:AnnotationProperty }
  ?iri a ?type .

  FILTER NOT EXISTS { 
      ?iri a owl:Class . 
      FILTER(?type = rdfs:Class) 
  }
  FILTER NOT EXISTS { 
      ?iri a ?specificProperty .
      VALUES ?specificProperty { owl:ObjectProperty owl:DatatypeProperty owl:AnnotationProperty }
      FILTER(?type = rdf:Property) 
  }
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
owl_declaration = """
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
ont_description = """
SELECT ?ont ?d
WHERE {
  ?ont a owl:Ontology .
    ?ont rdfs:comment|dcterms:abstract|dcterms:description|skos:definition|skos:note ?d .
}
"""

# ISU1 Missing Annotations
# Classes or properties lacking rdfs:label or rdfs:comment
isu1_missing_annotations = """
SELECT DISTINCT ?c ?p
WHERE {
  {
    VALUES ?type { owl:Class rdfs:Class }
    ?c a ?type .
    FILTER(isIRI(?c))
    FILTER (
      NOT EXISTS { ?c rdfs:label   ?lbl   } ||
      NOT EXISTS { ?c rdfs:comment ?cmt   }
    )
  }
  UNION
  {
    VALUES ?ptype { owl:ObjectProperty rdf:Property }
    ?p a ?ptype .
    FILTER(isIRI(?p))
    FILTER (
      NOT EXISTS { ?p rdfs:label   ?lbl2  } ||
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
class_labels = """
SELECT DISTINCT ?c ?lbl
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  ?c rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl
}
"""

property_missing_label = """
SELECT DISTINCT ?p
WHERE {
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
  ?p a ?type .
  FILTER NOT EXISTS { ?p rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl }
}
"""
property_labels = """
SELECT DISTINCT ?p ?lbl
WHERE {
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
  ?p a ?type .
  ?p rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl
}
"""

node_shape_missing_label = """
SELECT DISTINCT ?ns
WHERE {
  ?ns a sh:NodeShape .
  FILTER NOT EXISTS { ?ns sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl }
}
"""
node_shape_labels = """
SELECT DISTINCT ?ns ?lbl
WHERE {
  ?ns a sh:NodeShape .
  ?ns sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl
}
"""

property_shape_missing_label = """
SELECT ?ps
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
    FILTER NOT EXISTS { ?ps sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl }
}
"""
property_shape_labels = """
SELECT ?ps ?lbl
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
    ?ps sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?lbl
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
class_comments = """
SELECT DISTINCT ?c ?lbl
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  ?c a ?type .
  ?c rdfs:comment|dcterms:description|skos:definition ?lbl
}
"""

property_missing_comment = """
SELECT DISTINCT ?p
WHERE {
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
  ?p a ?type .
  FILTER NOT EXISTS { ?p rdfs:comment|dcterms:description|skos:definition ?lbl }
}
"""
property_comments = """
SELECT DISTINCT ?p ?lbl
WHERE {
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
  ?p a ?type .
  ?p rdfs:comment|dcterms:description|skos:definition ?lbl
}
"""

node_shape_missing_comment = """
SELECT DISTINCT ?ns
WHERE {
  ?ns a sh:NodeShape .
  FILTER NOT EXISTS { ?ns sh:description|rdfs:comment|dcterms:description|skos:definition ?lbl }
}
"""
node_shape_comments = """
SELECT DISTINCT ?ns ?lbl
WHERE {
  ?ns a sh:NodeShape .
  ?ns sh:description|rdfs:comment|dcterms:description|skos:definition ?lbl
}
"""

property_shape_missing_comment = """
SELECT DISTINCT ?ps
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
    FILTER NOT EXISTS { ?ps sh:description|rdfs:comment|dcterms:description|skos:definition ?lbl }
}
"""
property_shape_comments = """
SELECT DISTINCT ?ps ?lbl
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
    ?ps sh:description|rdfs:comment|dcterms:description|skos:definition ?lbl
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
    VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
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
      FILTER(isIRI(?c))
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
  VALUES ?type { owl:ObjectProperty owl:DatatypeProperty rdf:Property }
  ?p a ?type .
  ?p rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?label .
}
GROUP BY ?label
HAVING (COUNT(DISTINCT ?p) > 1)
"""

# NodeShapes with the same label
node_shape_same_label = """
SELECT ?label (GROUP_CONCAT(DISTINCT ?ns; separator=", ") AS ?nsList)
WHERE {
  ?ns a sh:NodeShape .
  ?ns sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?label .
}
GROUP BY ?label
HAVING (COUNT(DISTINCT ?ns) > 1)
"""

# PropertyShapes with the same label
property_shape_same_label = """
SELECT ?label (GROUP_CONCAT(DISTINCT ?ps; separator=", ") AS ?psList)
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
    ?ps sh:name|rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel ?label .
}
GROUP BY ?label
HAVING (COUNT(DISTINCT ?ps) > 1)
"""

# Untyped class
# Class without rdf:type owl:Class or rdfs:Class declaration
untyped_class = """
SELECT DISTINCT ?c
WHERE {
  { ?s rdfs:domain ?c . }
  UNION
  { ?s rdfs:range ?c . }
  UNION
  { ?s sh:class ?c . }
  
  # exclude blank nodes
  FILTER(isIRI(?c))

  # Restrict to ontology namespace
  ?ontology a owl:Ontology .
  FILTER(STRSTARTS(STR(?c), STR(?ontology)))

  MINUS { ?c rdf:type owl:Class }
  MINUS { ?c rdf:type rdfs:Class }

}
"""

# Untyped property
# Property without rdf:type rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration
untyped_property = """
SELECT DISTINCT ?p
WHERE {
  # Find resources used as predicates
  ?s ?p ?o .

  # exclude blank nodes
  FILTER(isIRI(?s))

  # Restrict to ontology namespace
  ?ontology a owl:Ontology .
  FILTER(STRSTARTS(STR(?c), STR(?ontology)))

  MINUS { ?p a rdf:Property }
  MINUS { ?p a owl:ObjectProperty }
  MINUS { ?p a owl:DatatypeProperty }

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
  # Filter resource URI from external namespaces
  ?ontology a owl:Ontology .
  FILTER(!CONTAINS(LCASE(STR(?resource)), LCASE(STR(?ontology))))
}
"""

# Namespace hijacking
# Define a class in the namespace using an external vocabulary prefix.
hijacking = """
SELECT ?namespace (COUNT(DISTINCT ?resource) AS ?count)
WHERE {
    ?resource ?property ?value .
    FILTER(isIRI(?resource))
    BIND(REPLACE(STR(?resource), "^(.*)[/#][^/#]*$", "$1") AS ?namespace)
    MINUS { ?resource rdf:type owl:Ontology }
}
GROUP BY ?namespace
"""

# Count SHACL Shapes
node_shape = """
SELECT (COUNT(DISTINCT ?ns) AS ?shapeCount)
WHERE {
  ?ns a sh:NodeShape .
}
"""
property_shape = """
SELECT (COUNT(DISTINCT ?ps) AS ?shapeCount)
WHERE {
    {
     	?ps a sh:PropertyShape  
    } UNION {
      	?ns sh:property ?ps .
      	FILTER(isBlank(?ps)) .
    }
}
"""

# Number of classes specified in NodeShapes
classes_in_node_shape = """
SELECT DISTINCT ?ns (COUNT(DISTINCT ?c) AS ?classCount)
WHERE {
  VALUES ?type { owl:Class rdfs:Class }
  {
    ?ns a sh:NodeShape, ?type .
    BIND (?ns as ?c)
  }
  UNION
  {
    ?ns a sh:NodeShape ;
          sh:targetClass ?c .
    ?c a ?type .
  }
} GROUP BY ?ns
"""

# Number of locally defined properties specified in PropertyShapes through sh:path
# The blank nodes created by sh:property in NodeShapes are also counted.
# This behaviour can be disabled with FILTER(isIRI(?ps)) 
property_in_property_shape = """
SELECT DISTINCT ?ps ?prop
WHERE {
  {
    ?ps a sh:PropertyShape .
  }
  UNION
  {
    # Include blank nodes that are not explicitly declared as a sh:PropertyShape
    ?ns a sh:NodeShape .
    ?ns sh:property ?propertyShape .
    ?propertyShape sh:path ?prop .
    BIND(?propertyShape AS ?ps)
  }
  ?ps sh:path ?prop .
  VALUES ?type { owl:ObjectProperty rdf:Property owl:DatatypeProperty }
  ?prop a ?type .
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

def qa_check_results(description,qan):
    print(f"\nCheck {qan}: {description}.")
    qan += 1
    return qan

def normalise(count, total):
    count = float(count)
    total = float(total)
    if total > 0:
        out = count / total
    else:
        out = 0
    if out > 0:
      out = f"{out:.3f}"
    else:
        out = 0
    return out

def print_profiling_table(metrics, violations):
    # Check if the ontology has been declared.
    if len(metrics['ontologyDeclared']) > 0:
        names = ""
        for name in metrics['ontologyDeclared']:
            names += f"{name},<br> "
        names = names.rstrip(",<br> ")
        
    print("\n## Profiling Metrics\n")
    print(f"| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape ", end="")
    print(f"| Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | ")
    print("|--|--|--|--|--|--|--|--|--|--|--|")
    print(f"| {names} | {metrics['triples']} | {metrics['classCount']} | {metrics['propertyCount']} | {metrics['nodeShapes']} | {metrics['propertyShapes']} | {metrics['classesInNodeShapes']} | {metrics['propertiesInPropertyShapes']} | {metrics['deprecatedClasses']} | {metrics['deprecatedProperties']} | {metrics['vocabulariesUsed']} |")

def print_qa_table(metrics, violations):
    print("\n## Quality Metrics\n")

    if metrics['ontologyDescription'] == 0:
      metrics['ontologyDescription'] = "yes"
    elif metrics['ontologyDescription'] == 1:
      metrics['ontologyDescription'] = "no"
    else:
      metrics['ontologyDescription'] = f"{metrics['ontologyDescription']} violations"

    print(f"| Name | Ontology Declared | Ontology Description | Class without label | Property without label | NodeShapes without label | PropertyShape without label ", end="")
    print(f"| Class without description | Property without description | NodeShapes without description | PropertyShape without description ", end="")
    print(f"| Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes ", end="")
    print(f"| Property without domain | Property without range ", end="")
    print(f"| Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |")
    print("|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|")
    print(f"| {name} | {ont} | {metrics['ontologyDescription']} | {normalise(metrics['missingClassLabel'],metrics['classCount'])} ", end="")
    print(f"| {normalise(metrics['missingPropertyLabel'],metrics['propertyCount'])} ", end="")
    print(f"| {normalise(metrics['missingNSLabel'],metrics['nodeShapes'])} ", end="")
    print(f"| {normalise(metrics['missingPSLabel'],metrics['propertyShapes'])} ", end="")
    print(f"| {normalise(metrics['missingClassDescription'],metrics['classCount'])} ", end="")
    print(f"| {normalise(metrics['missingPropertyDescription'],metrics['propertyCount'])} ", end="")
    print(f"| {normalise(metrics['missingNSDescription'],metrics['nodeShapes'])} ", end="")
    print(f"| {normalise(metrics['missingPSDescription'],metrics['propertyShapes'])} ", end="")
    print(f"| {normalise(metrics['nonUniqueClassLabels'],metrics['classCount'])} ", end="")
    print(f"| {normalise(metrics['nonUniquePropertyLabels'],metrics['propertyCount'])} ", end="")
    print(f"| {normalise(metrics['nonUniqueNSLabels'],metrics['nodeShapes'])} ", end="")
    print(f"| {normalise(metrics['nonUniquePSLabels'],metrics['propertyShapes'])} ", end="")
    print(f"| {normalise(metrics['isolatedClasses'],metrics['classCount'])} ", end="")
    print(f"| {normalise(metrics['missingDomain'],metrics['propertyCount'])} ", end="")
    print(f"| {normalise(metrics['missingRange'],metrics['propertyCount'])} ", end="")
    print(f"| {metrics['nonUniqueIdentifiers']} | {metrics['subclassCycles']} ", end="")
    print(f"| {metrics['untypedClasses']} | {metrics['untypedProperties']} | {metrics['hijacking']} |")

def sep():
    # print("\n","-"*20, sep="")
    print("\n","-"*20)

def write_ctrf_report(qa_metrics, qa_violations, ont, file_path, filename):
    """
    Convert QA metrics to CTRF (Common Test Result Format) JSON.
    """
    # Convert metrics to test cases (pass/fail based on violations)
    test_cases = []
    if ont == "yes":
        ont = 0
    else:
        ont = 1

    # Each QA check becomes a test case
    checks = [
        ("Ontology Declaration",             ont, qa_violations['ontologyDeclared']),
        ("Ontology Description",             qa_metrics['ontologyDescription'], qa_violations['ontologyDescription']), 
        ("Class without label",              qa_metrics['missingClassLabel'], qa_violations['missingClassLabel']), 
        ("Property without label",           qa_metrics['missingPropertyLabel'], qa_violations['missingPropertyLabel']), 
        ("NodeShape without label",          qa_metrics['missingNSLabel'], qa_violations['missingNSLabel']), 
        ("PropertyShape without label",      qa_metrics['missingPSLabel'], qa_violations['missingPSLabel']), 
        ("Class without description",        qa_metrics['missingClassDescription'], qa_violations['missingClassDescription']), 
        ("Property without description",     qa_metrics['missingPropertyDescription'], qa_violations['missingPropertyDescription']), 
        ("NodeShape without description",    qa_metrics['missingNSDescription'], qa_violations['missingNSDescription']), 
        ("PropertyShape without description",qa_metrics['missingPSDescription'], qa_violations['missingPSDescription']), 
        ("Non-Unique Class Labels",          qa_metrics['nonUniqueClassLabels'], qa_violations['nonUniqueClassLabels']), 
        ("Non-Unique Property Labels",       qa_metrics['nonUniquePropertyLabels'], qa_violations['nonUniquePropertyLabels']), 
        ("Non-Unique NodeShape Labels",      qa_metrics['nonUniqueNSLabels'], qa_violations['nonUniqueNSLabels']), 
        ("Non-Unique PropertyShape Labels",  qa_metrics['nonUniquePSLabels'], qa_violations['nonUniquePSLabels']), 
        ("Isolated Classes",                 qa_metrics['isolatedClasses'], qa_violations['isolatedClasses']), 
        ("Property without domain",          qa_metrics['missingDomain'], qa_violations['missingDomain']), 
        ("Property without range",           qa_metrics['missingRange'], qa_violations['missingRange']), 
        ("Non-Unique Identifiers",           qa_metrics['nonUniqueIdentifiers'], qa_violations['nonUniqueIdentifiers']), 
        ("Subclass Cycles",                  qa_metrics['subclassCycles'], qa_violations['subclassCycles']), 
        ("Untyped Classes",                  qa_metrics['untypedClasses'], qa_violations['untypedClasses']), 
        ("Untyped Properties",               qa_metrics['untypedProperties'], qa_violations['untypedProperties']), 
        ("Subclass Cycles",                  qa_metrics['subclassCycles'], qa_violations['subclassCycles'])
    #    ("Namespace Hijacking", qa_metrics['hijacking'])
    ]
    
    passed = 0
    failed = 0
    
    for check_name, violation_count, violation_element in checks:
        test_case = {
            "name": check_name,
            "status": "pass" if violation_count == 0 else "fail"
        }
        if violation_count > 0:
            test_case["failure"] = {
                "violations": violation_count,
                "elements": violation_element
            }
            failed += 1
        else:
            passed += 1
        test_cases.append(test_case)
    
    # Build CTRF report
    ctrf_report = {
        "results": {
            "tool": {
                "name": "Ontology QA",
                "version": "2025-11-17"
            },
            "summary": {
                "tests": len(test_cases),
                "passed": passed,
                "failed": failed
            },
            "tests": test_cases,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    # Write to file
    os.makedirs(file_path, exist_ok=True)
    output_file = os.path.join(file_path, filename)
    with open(output_file, 'w') as f:
        json.dump(ctrf_report, f, indent=2)
    
    print(f"\nCTRF report written to: {output_file}")
    return ctrf_report

def load_rdf_file(file, graph):
    """
    Load RDF data from a file into the given rdflib Graph.
    
    Args:
        file (str): Path to the RDF file.
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        bool: True if the file was successfully loaded, False otherwise.
    """
    print(f"Loading data from: {file}")

    # Try to guess format from file extension
    if file.lower().endswith(('.ttl', '.turtle')):
        fmt = "turtle"
    elif file.lower().endswith(('.rdf', '.owl', '.xml')):
        fmt = "xml"
    else:
        fmt = None  # Let rdflib try to guess
    try:
        graph.parse(file, format=fmt)
        return True
    except Exception as e:
        print(f"Failed to parse {file} ({fmt if fmt else 'auto'}): {e}")
        return False

def profiling(graph):
    """
    Compute profiling information for an RDF graph.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        metrics (dict): Count of variours metrics for ontology QA.
        violations (dict): List of elements violating the check.
    """
    metrics = {}
    violations = {}
    # Count initial classes, properties, and shapes.
    results = graph.query(count_cp)
    (row,) = results
    # print(f"RDF/OWL classes: {row.classCount}\nRDF/OWL properties: {row.propertyCount}")
    metrics['classCount']= row.classCount
    metrics['propertyCount'] = row.propertyCount
  
    results = graph.query(node_shape)
    if results:
        (row,) = results
        # print(f"SHACL Node Shapes: {row.shapeCount}")
        metrics['nodeShapes'] = row.shapeCount
    else:
        metrics['nodeShapes'] = 0
    results = graph.query(property_shape)
    if results:
        (row,) = results
        # print(f"SHACL Property Shapes: {row.shapeCount}")
        metrics['propertyShapes'] = row.shapeCount
    else:
        metrics['propertyShapes'] = 0
    
    # Count classes in NodeShapes.
    results = graph.query(classes_in_node_shape)
    total_classes_in_shapes = sum(int(row.classCount) for row in results)
    # print(f"Local classes in Node Shapes: {total_classes_in_shapes}")
    metrics['classesInNodeShapes'] = total_classes_in_shapes
    # if verbose and total_classes_in_shapes > 0:
    #     print("| NodeShape | Class count |\n|--|--|")
    #     for row in results:
    #         print(f"| {row.ns} | {row.classCount} |")
    # Count properties in PropertyShapes.
    results = graph.query(property_in_property_shape)
    total_properties_in_shapes = len(results)
    # print(f"Local properties in Property Shapes: {total_properties_in_shapes}")
    metrics['propertiesInPropertyShapes'] = total_properties_in_shapes
    # if results and verbose:
    #     print("| PropertyShape | Local Property |\n|--|--|")
    #     for row in results:
    #         print(f"| {row.ps} | {row.prop} |")
    # Number of Deprecated Classes and Properties
    results = graph.query(deprecated_class)
    metrics['deprecatedClasses'] = len(results)
    # print(f"Deprecated classes: {metrics['deprecatedClasses']}")
    # if verbose and int(metrics['deprecatedClasses']) > 0:
    #     print(f"List of deprecated classes:")
    #     for row in results:
    #         print(f" - {row.c}")
    results = graph.query(deprecated_property)
    metrics['deprecatedProperties'] = len(results)
    # print(f"Deprecated properties: {metrics['deprecatedProperties']}")
    # if verbose and int(metrics['deprecatedProperties']) > 0:
    #     print(f"List of deprecated properties:")
    #     for row in results:
    #         print(f" - {row.p}")
    # List all used prefixes
    active_prefixes = prefixes(graph)
    results = graph.query(owl_declaration)
    if results:
        for row in results:
            # Remove ontology namespace from active_prefixes
            to_remove = []
            for row in results:
                for pfx, ns in active_prefixes.items():
                    if str(row.ont) == ns: to_remove.append(pfx)
            for pfx in to_remove:
                del active_prefixes[pfx]
    metrics['vocabulariesUsed'] = len(active_prefixes)
    # print(f"External vocabularies declared: {metrics['vocabulariesUsed']}")
    violations['vocabulariesUsed'] = {
        'prefix': [],
        'uri': []
        }
    for pfx, ns in active_prefixes.items():
        # print(f" - {pfx}: {ns}")
        violations['vocabulariesUsed']['prefix'].append(pfx)
        violations['vocabulariesUsed']['uri'].append(ns)
    return metrics, violations

def inference(graph):
    """
    Infer sub-class relations from ...
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        graph (rdflib.Graph): The RDF graph, after inference applied.
    """
    print("\nApplying Subclass inference rule iteratively...")
    while True:
        inferred_triples_result = graph.query(subclass_inference_rule)
        if not inferred_triples_result:
            print("No new subclass inferences to add. Inference complete.")
            break
        graph_size_before = len(graph)
        for t in inferred_triples_result:
            graph.add(t)
        
        # Try replace the above with:
        # graph += inferred_triples_result
        graph_size_after = len(graph)
        if graph_size_after == graph_size_before:
            print("No new subclass inferences in this pass. Inference complete.")
            break
        else:
            print(f"Added {graph_size_after - graph_size_before} new triples. Continuing inference...")
    print(f"Final graph size after inference: {len(graph)} triples.")
    return graph      


def owl_declaration_description(graph, status):
    """
    Docstring for owl_declaration_description
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Count of variours metrics for ontology QA.
        violations (dict): List of elements violating the check.
        status (int): Number of violations after the check.
    """
    metrics = {}
    violations = {}
    status = 0
    results = graph.query(owl_declaration)
    metrics['ontologyDeclared'] = [ ]
    if not results:
        # print(f"VIOLATION - No `owl:Ontology` declaration found.")
        status += 1
    # elif len(results) == 1:
    #     (row,) = results
    #     print(f"PASS - Found 1 ontology with `owl:Ontology` declaration:\n - {row.ont}")
    #     metrics['ontologyDeclared'] = [ row.ont ]
    else:
        # print(f"WARNING - Found {len(results)} `owl:Ontology` declarations:")
        for row in results:
            # print(f" - {row.ont}")
            metrics['ontologyDeclared'].append(row.ont)
    # sep()

    if metrics['ontologyDeclared'][0] != 0:
      name = ", ".join(metrics['ontologyDeclared'])
      ont = "yes"
      violations['ontologyDeclared'] = ""
    else:
      name = metrics['filesProcessed'][0]
      violations['ontologyDeclared'] = name
      ont = "no"
    
    # Missing ontology description.
    if len(metrics['ontologyDeclared']) > 0:
        # qan = qa_check_results("Ontology description",qan)
        results = graph.query(no_ont_description)
        if not results:
            print("PASS - All ontologies have a description.")
            metrics['ontologyDescription'] = 0 # yes
            violations['ontologyDescription'] = ""
            # if args.verbose:
            #     results = graph.query(ont_description)
            #     print("\n**Ontology + Description:**")
            #     for row in results:
            #         print(f" - {row.ont}\n   {row.d}")
        else:
            owd = len(results)
            metrics['ontologyDescription'] = len(results) #  violations
            # print(f"VIOLATION - Found {len(results)} ontologies without any description:")
            status += 1
            string = ""
            for row in results:
                # print(f" - {row.ont}")
                string += f"{row.ont},<br> "
            string = string.rstrip(",<br> ")
            violations['ontologyDescription'] = string
    else:
        # print(f"\nSkipping check {qan}: Ontology description (no ontology declared).")
        qan += 1
        metrics['ontologyDescription'] = 1 # no
        violations['ontologyDescription'] = "No ontology declared"
    # sep()
    return metrics, violations, status

def load_from_directory(f):
    """
    Docstring for load_from_directory
    
    :param f: Description
    """
    counter = 0
    metrics = {}
    g = rdflib.Graph()
    # check if f is a directory
    if os.path.isdir(f):
        for root, _, files in os.walk(f):
            for file in files:
                file_path = os.path.join(root, file)
                if load_rdf_file(file_path, g):
                  # Append successfully processed file
                  metrics['filesProcessed'] = metrics.get('filesProcessed', []) + [file_path]
                  counter += 1
        # continue  # skip to next f after processing directory

    else:
        if load_rdf_file(f, g):
            # Append successfully processed file
            metrics['filesProcessed'] = metrics.get('filesProcessed', []) + [f]
            counter += 1
    return counter, metrics, g

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-e', '--exit-status', action='store_true', help='Report an exit status to determine if one or more violations were detected.')
    parser.add_argument('-v', '--verbose',action='store_true', help='Enable verbose output.')
    parser.add_argument('-p', '--profile-only',action='store_true', help='Compute only the profiling metrics and skip the QA part.')
    parser.add_argument('--ctrf-dir', type=str, default='./ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--ctrf-filename', type=str, default=None, help='Filename for CTRF report (if None, uses default pattern).')
    parser.add_argument('data_files', nargs='+', help='List of RDF files or folders to process.')
    args = parser.parse_args()

    # Create an empty dictionaries to store the ontology metrics.
    qa_metrics = {}    # violation_count
    qa_violations = {} # violation_elements

    # 1. Load Data
    g = rdflib.Graph()
    file_counter = 0
    # print(f"## Profiling Metrics\n")
    for f in args.data_files:
        c, file_metrics, file_graph = load_from_directory(f)
        file_counter += c
        qa_metrics.update(file_metrics)
        g += file_graph

    if file_counter == 0:
        print("ERROR - No RDF data in input files or directories.")
        return
    
    # Store the profiling metrics.
    qa_metrics['triples']= len(g)
    # sep()
    # print(f"\nInitial graph size: {qa_metrics['triples']} triples")
    
   # 2. Simulate Inference
    metrics, violations = profiling(g)
    g = inference(g)
    qa_metrics.update(metrics)
    qa_violations.update(violations)
    
    

    # Compute the metrics for Quality Assurance.
    # sep()
    # print("\n## QA Metrics")
    xs = 0  # Number of violations, to decide the exit-status flag.
    qan = 1 # Counter for the tests executed (to discard later)
    tests = [] # Name and order of tests executed (new counter).

    # Check for OWL ontology declaration
    # qan = qa_check_results("OWL ontology declaration",qan)
    tests.append("OWL ontology declaration")
    tests.append("Ontology description")
    
    metrics, violations, xs = owl_declaration_description(g, xs)
    qa_metrics.update(metrics)
    qa_violations.update(violations)

    # Terminate the execution if further QA checks are not required.
    if args.profile_only:
        print("\nProfile-only mode enabled. Skipping additional QA checks.")
        print_profiling_table(qa_metrics, qa_violations)
        return
    
    # Missing Annotations
    qan = qa_check_results("Classes missing label annotations",qan)
    results = g.query(class_missing_label)
    qa_metrics['missingClassLabel'] = 0
    qa_violations['missingClassLabel'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - All classes have a label annotation.")
        if args.verbose:
            results = g.query(class_labels)
            print("|  Class | Label |\n|--|--|")
            for row in results:
                print(f"| {row.c} | {row.lbl} |")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['missingClassLabel'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingClassLabel']} classes missing a label annotation:")
        xs += 1
        string = ""
        for t in results:
          print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingClassLabel'] = string
    sep()

    qan = qa_check_results("Properties missing label annotations",qan)
    results = g.query(property_missing_label)
    qa_metrics['missingPropertyLabel'] = 0
    qa_violations['missingPropertyLabel'] = ""
    if not results and int(qa_metrics['propertyCount']) > 0:
        print("PASS - All properties have a label annotation.")
        if args.verbose:
            results = g.query(property_labels)
            print("|  Property | Label |\n|--|--|")
            for row in results:
                print(f"| {row.p} | {row.lbl} |")
    elif not results:
        print("WARNING - No properties defined, invalid metric.")
    else:
        qa_metrics['missingPropertyLabel'] = len(results)
        print(f"VIOLATION - Found {qa_metrics['missingPropertyLabel']} properties missing a label annotation.")
        xs += 1
        string = ""
        for t in results:
          print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingPropertyLabel'] = string
    sep()

    qan = qa_check_results("NodeShape missing label annotations",qan)
    results = g.query(node_shape_missing_label)
    qa_metrics['missingNSLabel'] = 0
    qa_violations['missingNSLabel'] = ""
    if not results and int(qa_metrics['nodeShapes']) > 0:
        print("PASS - All NodeShape have a label annotation.")
        if args.verbose and int(qa_metrics['nodeShapes']) > 0:
            results = g.query(node_shape_labels)
            print("|  NodeShape | Label |\n|--|--|")
            for row in results:
                print(f"| {row.ns} | {row.lbl} |")
    elif not results:
        print("WARNING - No NodeShape defined, invalid metric.")
    else:
        qa_metrics['missingNSLabel'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingNSLabel']} NodeShape missing a label annotation.")
        for row in results:
          print(f" - {row.ns}")
          string += f"{row.ns},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingNSLabel'] = string
    sep()

    qan = qa_check_results("PropertyShape missing label annotations",qan)
    results = g.query(property_shape_missing_label)
    qa_metrics['missingPSLabel'] = 0
    qa_violations['missingPSLabel'] = ""
    if not results and int(qa_metrics['propertyShapes']) > 0:
        print("PASS - All PropertyShape have a label annotation.")
        if args.verbose:
            results = g.query(property_shape_labels)
            print("|  PropertyShape | Label |\n|--|--|")
            for row in results:
                print(f"| {row.ps} | {row.lbl} |")
    elif not results:
        print("WARNING - No PropertyShapes defined, invalid metric.")
    else:
        qa_metrics['missingPSLabel'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingPSLabel']} PropertyShape missing a label annotation.")
        for row in results:
          print(f" - {row.ps}")
          string += f"{row.ps},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingPSLabel'] = string
    sep()

    qan = qa_check_results("Classes missing description annotations",qan)
    results = g.query(class_missing_comment)
    qa_metrics['missingClassDescription'] = 0
    qa_violations['missingClassDescription'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - All classes have a description annotation.")
        if args.verbose:
            results = g.query(class_labels)
            print("|  Class | Description |\n|--|--|")
            for row in results:
                print(f"| {row.c} | {row.lbl} |")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['missingClassDescription'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingClassDescription']} classes missing a description annotation:")
        for t in results:
          print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingClassDescription'] = string
    sep()

    qan = qa_check_results("Properties missing description annotations",qan)
    results = g.query(property_missing_comment)
    qa_metrics['missingPropertyDescription'] = 0
    qa_violations['missingPropertyDescription'] = ""
    if not results and int(qa_metrics['propertyCount']) > 0:
        print("PASS - All properties have a description annotation.")
        if args.verbose:
            results = g.query(class_labels)
            print("| Property | Description |\n|--|--|")
            for row in results:
                print(f"| {row.p} | {row.lbl} |")
    elif not results:
        print("WARNING - No properties defined, invalid metric.")
    else:
        qa_metrics['missingPropertyDescription'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingPropertyDescription']} properties missing a description annotation.")
        for t in results:
          print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingPropertyDescription'] = string
    sep()

    qan = qa_check_results("NodeShape missing description annotations",qan)
    results = g.query(node_shape_missing_comment)
    qa_metrics['missingNSDescription'] = 0
    qa_violations['missingNSDescription'] = ""
    if not results and int(qa_metrics['nodeShapes']) > 0:
        print("PASS - All NodeShape have a description annotation.")
        if args.verbose:
            results = g.query(node_shape_labels)
            print("| NodeShape | Description |\n|--|--|")
            for row in results:
                print(f"| {row.ns} | {row.lbl} |")
    elif not results:
        print("WARNING - No NodeShape defined, invalid metric.")
    else:
        qa_metrics['missingNSDescription'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingNSDescription']} NodeShape missing a description annotation:")
        for row in results:
          print(f" - {row.ns}")
          string += f"{row.ns},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingNSDescription'] = string
    sep()

    qan = qa_check_results("PropertyShape missing description annotations",qan)
    results = g.query(property_shape_missing_comment)
    qa_metrics['missingPSDescription'] = 0
    qa_violations['missingPSDescription'] = ""
    if not results and int(qa_metrics['propertyShapes']) > 0:
        print("PASS - All PropertyShape have a description annotation.")
        if args.verbose:
            results = g.query(property_shape_labels)
            print("| PropertyShape | Description |\n|--|--|")
            for row in results:
                print(f"| {row.ps} | {row.lbl} |")
    elif not results:
        print("WARNING - No PropertyShapes defined, invalid metric.")
    else:
        qa_metrics['missingPSDescription'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['missingPSDescription']} PropertyShape missing a description annotation:")
        for row in results:
          print(f" - {row.ps}")
          string += f"{row.ps},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['missingPSDescription'] = string
    sep()

    qan = qa_check_results("Classes with the same label",qan)
    results = g.query(class_same_label)
    qa_metrics['nonUniqueClassLabels'] = 0
    qa_violations['nonUniqueClassLabels'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - No classes share the same label.")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['nonUniqueClassLabels'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['nonUniqueClassLabels']} labels shared by multiple classes.")
        print("| Label | Classes |\n|--|--|")
        for row in results:
            print(f"| {row.label} | {row.classes} |")
            string += f"\"{row.label}\": {row.classes};<br> "
        string = string.rstrip(";<br> ")
        qa_violations['nonUniqueClassLabels'] = string
    sep()

    qan = qa_check_results("Properties with the same label",qan)
    results = g.query(property_same_label)
    qa_metrics['nonUniquePropertyLabels'] = 0
    qa_violations['nonUniquePropertyLabels'] = ""
    if not results and int(qa_metrics['propertyCount']) > 0:
        print("PASS - No property share the same label.")
    elif not results:
        print("WARNING - No properties defined, invalid metric.")
    else:
        qa_metrics['nonUniquePropertyLabels'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['nonUniquePropertyLabels']} labels shared by multiple properties.")
        print("| Label | Properties |\n|--|--|")
        for row in results:
            print(f"| {row.label} | {row.properties} |")
            string += f"\"{row.label}\": {row.properties};<br> "
        string = string.rstrip(";<br> ")
        qa_violations['nonUniquePropertyLabels'] = string
    sep()

    qan = qa_check_results("NodeShapes with the same label",qan)
    results = g.query(node_shape_same_label)
    qa_metrics['nonUniqueNSLabels'] = 0
    qa_violations['nonUniqueNSLabels'] = ""
    if not results and int(qa_metrics['nodeShapes']) > 0:
        print("PASS - No NodeShape share the same label.")
    elif not results:
        print("WARNING - No NodeShape defined, invalid metric.")
    else:
        qa_metrics['nonUniqueNSLabels'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['nonUniqueNSLabels']} labels shared by multiple NodeShapes.")
        print("| Label | NodeShapes |\n|--|--|")
        for row in results:
            print(f"| {row.label} | {row.nsList} |")
            string += f"\"{row.label}\": {row.nsList};<br> "
        string = string.rstrip(";<br> ")
        qa_violations['nonUniqueNSLabels'] = string
    sep()

    qan = qa_check_results("PropertyShapes with the same label",qan)
    results = g.query(property_shape_same_label)
    qa_metrics['nonUniquePSLabels'] = 0
    qa_violations['nonUniquePSLabels'] = ""
    if not results:
        print("PASS - No PropertyShape share the same label.")
    elif not results:
        print("WARNING - No PropertyShapes defined, invalid metric.")
    else:
        qa_metrics['nonUniquePSLabels'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['nonUniquePSLabels']} labels shared by multiple PropertyShapes.")
        print("| Label | PropertyShapes |\n|--|--|")
        for row in results:
            print(f"| {row.label} | {row.psList} |")
            string += f"\"{row.label}\": {row.psList};<br> "
        string = string.rstrip(";<br> ")
        qa_violations['nonUniquePSLabels'] = string
    sep()

    # Number of Isolated Classes
    qan = qa_check_results("Number of isolated classes",qan)
    results = g.query(isolated_classes)
    qa_metrics['isolatedClasses'] = 0
    qa_violations['isolatedClasses'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - All classes are connected to another class through a subclass or property relation.")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['isolatedClasses'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['isolatedClasses']} isolated classes:")
        for row in results:
          print(f" - {row[0]}")
          string += f"{row[0]},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['isolatedClasses'] = string
    sep()

    # Missing Domain or Range in Properties
    qan = qa_check_results("Missing Domain or Range in Properties",qan)
    results = g.query(ic2_missing_dr_property)
    dCount = 0
    rCount = 0
    qa_metrics['missingDomainRange'] = 0
    if not results and int(qa_metrics['propertyCount']) > 0:
        print("PASS - All properties have domain and range defined.")
    elif not results:
        print("WARNING - No properties defined, invalid metric.")
    else:
        qa_metrics['missingDomainRange'] = len(results)
        xs += 1
        string = ""
        string2 = ""
        print(f"VIOLATION - Found {qa_metrics['missingDomainRange']} properties without `rdfs:domain` or `rdfs:range` declaration:")
        print(f"| Property | Domain | Range |\n| -------- | ------ | ----- |")
        for row in results:
            predicate = row.p
            if row.domain:
                domain = row.domain
            else:
                domain = 'None'
                dCount += 1
                string += f"{predicate},<br> "
            if row.range:
                prange = row.range
            else:
                prange = 'None'
                rCount += 1
                string2 += f"{predicate},<br> "
            print(f"| {predicate} | {domain} | {prange} |")
    if dCount > 0:
        string = string.rstrip(",<br> ")
        qa_violations['missingDomain'] = string
    else:
        qa_violations['missingDomain'] = ""
    if rCount > 0:
        string2 = string2.rstrip(",<br> ")
        qa_violations['missingRange'] = string2
    else:
        qa_violations['missingRange'] = ""
    qa_metrics['missingDomain'] = dCount
    qa_metrics['missingRange']  = rCount
    sep()

    # Non-unique identifiers
    qan = qa_check_results("Non-unique identifiers",qan)
    results = g.query(unique_identifiers)
    if not results:
        print("PASS - No violations found.")
        qa_metrics['nonUniqueIdentifiers'] = 0
        qa_violations['nonUniqueIdentifiers'] = ""
    else:
        qa_metrics['nonUniqueIdentifiers'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['nonUniqueIdentifiers']} elements with non-unique identifiers.")
        print("| URI | Declared as |\n|--|--|")
        for row in results:
            print(f"| {row.iri} | {row.declaredAs} |")
            string += f"{row.iri},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['nonUniqueIdentifiers'] = string
    sep()

    # IO2 Including Cycles in a Class Hierarchy
    qan = qa_check_results("Including Cycles in a Class Hierarchy",qan)
    results = g.query(io2_cycles)
    qa_metrics['subclassCycles'] = 0
    qa_violations['subclassCycles'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - No violations found.")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['subclassCycles'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['subclassCycles']} classes involved in subclass cycles:")
        for row in results:
            print(f" - {row.c}")
            string += f"{row.c},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['subclassCycles'] = string
    sep()

    # Untyped class
    qan = qa_check_results("Untyped class",qan)
    results = g.query(untyped_class)
    qa_metrics['untypedClasses'] = 0
    qa_violations['untypedClasses'] = ""
    if not results and int(qa_metrics['classCount']) > 0:
        print("PASS - No violations found.")
    elif not results:
        print("WARNING - No classes defined, invalid metric.")
    else:
        qa_metrics['untypedClasses'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['untypedClasses']} classes without `rdf:type`, `owl:Class`, or `rdfs:Class` declaration:")
        for row in results:
            print(f" - {row.c}")
            string += f"{row.c},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['untypedClasses'] = string
    if qa_metrics['ontologyDeclared'][0] == 0:
      print(f"WARNING - ontology namespace undefined. No way to confirm if the class is defined in the ontology or an external vocabulary.")
    sep()

     # Untyped property
    qan = qa_check_results("Untyped property",qan)
    results = g.query(untyped_property)
    qa_metrics['untypedProperties'] = 0
    qa_violations['untypedProperties'] = ""
    if not results and int(qa_metrics['propertyCount']) > 0:
        print("PASS - No violations found.")
    elif not results:
        print("WARNING - No properties defined, invalid metric.")
    else:
        qa_metrics['untypedProperties'] = len(results)
        xs += 1
        string = ""
        print(f"VIOLATION - Found {qa_metrics['untypedProperties']} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:")
        for row in results:
            print(f" - {row.p}")
            string += f"{row.p},<br> "
        string = string.rstrip(",<br> ")
        qa_violations['untypedProperties'] = string
    if qa_metrics['ontologyDeclared'][0] == 0:
      print(f"WARNING - ontology namespace undefined. No way to confirm if the property is defined in the ontology or an external vocabulary.")
    sep()

     # Namespace hijacking
    qan = qa_check_results("Namespace hijacking",qan)
    results = g.query(hijacking)
    if not results:
        print("PASS - No violations found.") # For now, this condition is never met.
        qa_metrics['hijacking'] = 0
    else:
        qa_metrics['hijacking'] = len(results)
        # print(f"VIOLATION - Found {qa_metrics['hijacking']} resources defined using an external vocabulary prefix:")
        print(f"WARNING - Found resources defined in {qa_metrics['hijacking']} namespaces. Count of entities for each namespace:")
        for row in results:
            print(f" - {row.namespace} {row['count']}")
    sep()

    ################################################################################
    # Print a summary of the profiling and quality metrics in a markdown table format.
       
    # Profiling
    print_profiling_table(qa_metrics, qa_violations)

    # QA metrics
    print_qa_table(qa_metrics.copy(), qa_violations)

    # Generate CTRF report
    # Determine CTRF filename
    if args.ctrf_filename:
        ctrf_filename = args.ctrf_filename
    else:
        ctrf_filename = f'ontology-qa-report-{os.getpid()}.json'
    
    write_ctrf_report(qa_metrics, qa_violations , ont, args.ctrf_dir, ctrf_filename)

    # Exit status
    if args.exit_status: sys.exit(xs)

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
