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
missing_dr_property = """
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
subclass_cycles = """
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

# Return OWL ontology declaration
owl_declaration = """
SELECT ?ont
WHERE {
  ?ont a owl:Ontology .
}
"""

# Return ontology without description
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
# Class without owl:Class or rdfs:Class declaration
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
# Property without rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration
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
    if count == total: out = 1
    return out

def get_ontology_name(metrics):
    # Retrieve the ontology name from URI (if declared) or file.
    names = ""
    count = 0
    for _ in range(len(metrics['filesProcessed'])):
        if metrics['ontologyURI'][_]:
            names += f"{metrics['ontologyURI'][_]},<br> "
        else:
            count += 1
        
    if count == 1:
        names += f"{count} URI not found.,<br> "
    elif count > 1:
        names += f"{count} URIs not found.,<br> "
    names = names.rstrip(",<br> ")
    return names

def qa_terminate(file, log):
    """
    Print the results to a file name if specified, otherwise print to the STDOUT.

    Args:
        file (str): Name of the output file. If undefined, print to the STDOUT.
        log (str): Results of the Quality Assurance tests, formatted in markdown.
    """
    # Print output to file or STDOUT.
    if file:
        with open(file, "w", encoding="utf-8") as f:
            f.write(log)
    else:
        print(log)

def print_profiling_table(metrics):
    """
    Print a table with the profiling metrics of an RDF graph.

    Args:
        metrics (dict): Number of violations for various ontology metrics.
    
    Returns:
        log (str): Pretty table with results.
    """

    name = get_ontology_name(metrics)
    log = "\n## Profiling Metrics\n"
    log += f"| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape "
    log += f"| Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {metrics['triples']} | {metrics['classCount']} | {metrics['propertyCount']} | {metrics['nodeShapes']} | {metrics['propertyShapes']} | {metrics['classesInNodeShapes']} | {metrics['propertiesInPropertyShapes']} | {metrics['deprecatedClasses']} | {metrics['deprecatedProperties']} | {metrics['vocabulariesUsed']} |\n"
    return log

def print_qa_table(metrics):
    """
    Print a table with the quality assurance metrics of an RDF graph.

    Args:
        metrics (dict): Number of violations for various ontology metrics.
    
    Returns:
        log (str): Pretty table with results.
    """
    name = get_ontology_name(metrics)
    log = "\n## Quality Metrics\n"
    log += f"| Name | Ontology not declared | Ontology without description | Class without label | Property without label | NodeShapes without label | PropertyShape without label "
    log += f"| Class without description | Property without description | NodeShapes without description | PropertyShape without description "
    log += f"| Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes "
    log += f"| Property without domain | Property without range "
    log += f"| Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |\n"
    log += "|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|\n"
    log += f"| {name} | {normalise(metrics['ontologyNotDeclared'],len(metrics['filesProcessed']))} "
    log += f"| {normalise(metrics['ontologyDescription'],len(metrics['filesProcessed']))} "
    log += f"| {normalise(metrics['missingClassLabel'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingPropertyLabel'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingNSLabel'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['missingPSLabel'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['missingClassDescription'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingPropertyDescription'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingNSDescription'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['missingPSDescription'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['nonUniqueClassLabels'],metrics['classCount'])} "
    log += f"| {normalise(metrics['nonUniquePropertyLabels'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['nonUniqueNSLabels'],metrics['nodeShapes'])} "
    log += f"| {normalise(metrics['nonUniquePSLabels'],metrics['propertyShapes'])} "
    log += f"| {normalise(metrics['isolatedClasses'],metrics['classCount'])} "
    log += f"| {normalise(metrics['missingDomain'],metrics['propertyCount'])} "
    log += f"| {normalise(metrics['missingRange'],metrics['propertyCount'])} "
    log += f"| {metrics['nonUniqueIdentifiers']} | {metrics['subclassCycles']} "
    log += f"| {metrics['untypedClasses']} | {metrics['untypedProperties']} | {metrics['hijacking']} |\n"
    return log

def sep():
    return "\n"+"-"*20

def write_ctrf_report(metrics, violations, file_path, filename):
    """
    Convert QA metrics to CTRF (Common Test Result Format) JSON.
    """

    # Each QA check becomes a test case
    checks = [
        ("Ontology without declaration",     metrics['ontologyNotDeclared'],        violations['ontologyNotDeclared']),
        ("Ontology without description",     metrics['ontologyDescription'],        violations['ontologyDescription']), 
        ("Class without label",              metrics['missingClassLabel'],          violations['missingClassLabel']), 
        ("Property without label",           metrics['missingPropertyLabel'],       violations['missingPropertyLabel']), 
        ("NodeShape without label",          metrics['missingNSLabel'],             violations['missingNSLabel']), 
        ("PropertyShape without label",      metrics['missingPSLabel'],             violations['missingPSLabel']), 
        ("Class without description",        metrics['missingClassDescription'],    violations['missingClassDescription']), 
        ("Property without description",     metrics['missingPropertyDescription'], violations['missingPropertyDescription']), 
        ("NodeShape without description",    metrics['missingNSDescription'],       violations['missingNSDescription']), 
        ("PropertyShape without description",metrics['missingPSDescription'],       violations['missingPSDescription']), 
        ("Non-Unique Class Labels",          metrics['nonUniqueClassLabels'],       violations['nonUniqueClassLabels']), 
        ("Non-Unique Property Labels",       metrics['nonUniquePropertyLabels'],    violations['nonUniquePropertyLabels']), 
        ("Non-Unique NodeShape Labels",      metrics['nonUniqueNSLabels'],          violations['nonUniqueNSLabels']), 
        ("Non-Unique PropertyShape Labels",  metrics['nonUniquePSLabels'],          violations['nonUniquePSLabels']), 
        ("Isolated Classes",                 metrics['isolatedClasses'],            violations['isolatedClasses']), 
        ("Property without domain",          metrics['missingDomain'],              violations['missingDomain']), 
        ("Property without range",           metrics['missingRange'],               violations['missingRange']), 
        ("Non-Unique Identifiers",           metrics['nonUniqueIdentifiers'],       violations['nonUniqueIdentifiers']), 
        ("Subclass Cycles",                  metrics['subclassCycles'],             violations['subclassCycles']), 
        ("Untyped Classes",                  metrics['untypedClasses'],             violations['untypedClasses']), 
        ("Untyped Properties",               metrics['untypedProperties'],          violations['untypedProperties']), 
        ("Subclass Cycles",                  metrics['subclassCycles'],             violations['subclassCycles']),
        ("Namespace Hijacking",              metrics['hijacking'],                  violations['hijacking'])
    ]
    
    passed = 0
    failed = 0
    test_cases = []
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
    # Fallback CTRF filename
    if not filename:
        filename = f'ontology-qa-report-{os.getpid()}.json'
    output_file = os.path.join(file_path, filename)
    with open(output_file, 'w') as f:
        json.dump(ctrf_report, f, indent=2)
    
    log = f"\nCTRF report written to: {output_file}\n"
    return ctrf_report, log

def print_profiling_metrics(metrics, violations, verbose):
    log  = f"RDF/OWL classes: {metrics['classCount']}\n"
    log += f"RDF/OWL properties: {metrics['propertyCount']}\n"
    log += f"SHACL Node Shapes: {metrics['nodeShapes']}\n"
    log += f"SHACL Property Shapes: {metrics['propertyShapes']}\n"

    log += f"Local classes in Node Shapes: {metrics['classesInNodeShapes']}\n"
    if verbose and metrics['classesInNodeShapes'] > 0:
        log += "\n| NodeShape | Class count |\n|--|--|\n"
        for _ in range( len(violations['classesInNodeShapes']['ns']) ):
            log += f"| {violations['classesInNodeShapes']['ns'][_]} "
            log += f"| {violations['classesInNodeShapes']['classCount'][_]} |\n"
        log += "\n"

    log += f"Local properties in Property Shapes: {metrics['propertiesInPropertyShapes']}\n"
    if verbose and metrics['propertiesInPropertyShapes'] > 0:
        log += "\n| PropertyShape | Local Property |\n|--|--|\n"
        for _ in range( len(violations['propertiesInPropertyShapes']['ps']) ):
            log += f"| {violations['propertiesInPropertyShapes']['ps'][_]} "
            log += f"| {violations['propertiesInPropertyShapes']['propCount'][_]} |\n"
        log += "\n"
    
    log += f"Deprecated classes: {metrics['deprecatedClasses']}\n"
    if verbose and metrics['deprecatedClasses'] > 0:
        log += "List of deprecated classes:\n"
        for _ in range( len(violations['deprecatedClasses']) ):
            log += f" - {violations['deprecatedClasses'][_]}\n"
        log += "\n"
    
    log += f"Deprecated properties: {metrics['deprecatedProperties']}\n"
    if verbose and metrics['deprecatedProperties'] > 0:
        log += "List of deprecated properties:\n"
        for _ in range( len(violations['deprecatedProperties']) ):
            log += f" - {violations['deprecatedProperties'][_]}\n"
        log += "\n"

    log += f"External vocabularies declared: {metrics['vocabulariesUsed']}\n"
    if metrics['vocabulariesUsed'] > 0:
        log += "\n| Prefix | URI |\n|--|--|\n"
        for _ in range( len(violations['vocabulariesUsed']['prefix']) ):
            # print(f" - {pfx}: {ns}")
            log += f"| {violations['vocabulariesUsed']['prefix'][_]} "
            log += f"| {violations['vocabulariesUsed']['uri'][_]} |\n"
        log += "\n"

    return log

def print_qa_results(metrics, violations, checklist, verbose):
    log  = f"\n"

    return log

def profiling(graph):
    """
    Compute profiling information for an RDF graph.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
    """
    metrics = {}
    violations = {}

    # Count classes, properties before inferencing.
    results = graph.query(count_cp)
    (row,) = results
    metrics['classCount']= row.classCount
    metrics['propertyCount'] = row.propertyCount

    # Count shapes.
    results = graph.query(node_shape)
    if results:
        (row,) = results
        metrics['nodeShapes'] = row.shapeCount
    else:
        metrics['nodeShapes'] = 0
    results = graph.query(property_shape)
    if results:
        (row,) = results
        metrics['propertyShapes'] = row.shapeCount
    else:
        metrics['propertyShapes'] = 0
    
    # Count classes in NodeShapes.
    results = graph.query(classes_in_node_shape)
    total_classes_in_shapes = sum(int(row.classCount) for row in results)
    metrics['classesInNodeShapes'] = total_classes_in_shapes
    if total_classes_in_shapes > 0:
        violations['classesInNodeShapes'] = {
            'ns': [],
            'classCount': []
            }
        for row in results:
            violations['classesInNodeShapes']['ns'].append(row.ns)
            violations['classesInNodeShapes']['classCount'].append(row.classCount)

    # Count properties in PropertyShapes.
    results = graph.query(property_in_property_shape)
    total_properties_in_shapes = len(results)
    metrics['propertiesInPropertyShapes'] = total_properties_in_shapes
    if total_properties_in_shapes > 0:
        violations['propertiesInPropertyShapes'] = {
            'ps': [],
            'propCount': []
            }
        for row in results:
            violations['propertiesInPropertyShapes']['ps'].append(row.ps)
            violations['propertiesInPropertyShapes']['propCount'].append(row.prop)

    # Number of Deprecated Classes and Properties
    results = graph.query(deprecated_class)
    metrics['deprecatedClasses'] = len(results)
    if metrics['deprecatedClasses'] > 0:
        violations['deprecatedClasses'] = []
        for row in results:
            violations['deprecatedClasses'].append(row.c)
    results = graph.query(deprecated_property)
    metrics['deprecatedProperties'] = len(results)
    if metrics['deprecatedProperties'] > 0:
        violations['deprecatedProperties'] = []
        for row in results:
            violations['deprecatedProperties'].append(row.p)

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

    # These are not violations, but the dictionary is nevertheless used to store elements
    # matching the same key of the metrics dictionary.
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
        log (str): Result of inferencing.
    """
    log = "\nApplying Subclass inference rule iteratively...\n"
    while True:
        inferred_triples_result = graph.query(subclass_inference_rule)
        if not inferred_triples_result:
            log += "No new subclass inferences to add. Inference complete.\n"
            break
        graph_size_before = len(graph)
        for t in inferred_triples_result:
            graph.add(t)
        
        # Try replace the above with:
        # graph += inferred_triples_result
        graph_size_after = len(graph)
        if graph_size_after == graph_size_before:
            log += "No new subclass inferences in this pass. Inference complete.\n"
            break
        else:
            log += f"Added {graph_size_after - graph_size_before} new triples. Continuing inference...\n"
    log += f"Final graph size after inference: {len(graph)} triples.\n"
    return graph, log

def check_owl_declaration_description(graph, num_files, status):
    """
    QA test veriying that the ontology has a namespace declared as `owl:Ontology` and also contain a description.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        num_files (int): Number of RDF files loaded in the graph.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    metrics['ontologyNotDeclared'] = num_files # Assume no ontology has been declared.
    metrics['ontologyURI'] = [ ]

    # Check the ontology declaration.
    results = graph.query(owl_declaration)
    if not results:
        # print(f"VIOLATION - No `owl:Ontology` declaration found.") 
        status += 1
    else:
        for row in results:
            # print(f" - {row.ont}")
            metrics['ontologyURI'].append(row.ont)
            metrics['ontologyNotDeclared'] -= 1
    # Record the violation element (to improve).
    if metrics['ontologyNotDeclared'] == num_files:
        violations['ontologyNotDeclared'] = "all"
    elif  metrics['ontologyNotDeclared'] > 0 and  metrics['ontologyNotDeclared'] < num_files:
        violations['ontologyNotDeclared'] = "some"
    else:
        violations['ontologyNotDeclared'] = ""
    
    # Check the ontology description.
    if metrics['ontologyNotDeclared'] == num_files:
        # print(f"\nSkipping check {qan}: Ontology description (no ontology declared).")
        # qan += 1
        metrics['ontologyDescription'] = 1 # no
        violations['ontologyDescription'] = "No ontology declared"
    else:
        # qan = qa_check_results("Ontology description",qan)
        results = graph.query(no_ont_description)
        if not results:
            # print("PASS - All ontologies have a description.")
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
    return metrics, violations, status

def check_class_missing_label(graph, status):
    """
    QA test counting classes without a label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(class_missing_label)
    metrics['missingClassLabel'] = 0
    violations['missingClassLabel'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - All classes have a label annotation.")
    #     if args.verbose:
    #         results = graph.query(class_labels)
    #         print("|  Class | Label |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.c} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['missingClassLabel'] = len(results)
        # print(f"VIOLATION - Found {metrics['missingClassLabel']} classes missing a label annotation:")
        status += 1
        string = ""
        for t in results:
        #   print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['missingClassLabel'] = string
    return metrics, violations, status

def check_property_missing_label(graph, status):
    """
    QA test counting properties without a label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_missing_label)
    metrics['missingPropertyLabel'] = 0
    violations['missingPropertyLabel'] = ""
    # if not results and int(metrics['propertyCount']) > 0:
    #     print("PASS - All properties have a label annotation.")
    #     if args.verbose:
    #         results = graph.query(property_labels)
    #         print("|  Property | Label |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.p} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No properties defined, invalid metric.")
    # else:
    if results:
        metrics['missingPropertyLabel'] = len(results)
        # print(f"VIOLATION - Found {metrics['missingPropertyLabel']} properties missing a label annotation.")
        status += 1
        string = ""
        for t in results:
        #   print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPropertyLabel'] = string
    return metrics, violations, status

def check_node_shape_missing_label(graph, status):
    """
    QA test counting node shapes without a label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(node_shape_missing_label)
    metrics['missingNSLabel'] = 0
    violations['missingNSLabel'] = ""
    # if not results and int(metrics['nodeShapes']) > 0:
    #     print("PASS - All NodeShape have a label annotation.")
    #     if args.verbose and int(metrics['nodeShapes']) > 0:
    #         results = graph.query(node_shape_labels)
    #         print("|  NodeShape | Label |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.ns} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No NodeShape defined, invalid metric.")
    # else:
    if results:
        metrics['missingNSLabel'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingNSLabel']} NodeShape missing a label annotation.")
        for row in results:
        #   print(f" - {row.ns}")
          string += f"{row.ns},<br> "
        string = string.rstrip(",<br> ")
        violations['missingNSLabel'] = string
    return metrics, violations, status

def check_property_shape_missing_label(graph, status):
    """
    QA test counting property shapes without a label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_shape_missing_label)
    metrics['missingPSLabel'] = 0
    violations['missingPSLabel'] = ""
    # if not results and int(metrics['propertyShapes']) > 0:
    #     print("PASS - All PropertyShape have a label annotation.")
    #     if args.verbose:
    #         results = graph.query(property_shape_labels)
    #         print("|  PropertyShape | Label |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.ps} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No PropertyShapes defined, invalid metric.")
    # else:
    if results:
        metrics['missingPSLabel'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingPSLabel']} PropertyShape missing a label annotation.")
        for row in results:
        #   print(f" - {row.ps}")
          string += f"{row.ps},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPSLabel'] = string
    return metrics, violations, status

def check_class_missing_comment(graph, status):
    """
    QA test counting classes without description.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(class_missing_comment)
    metrics['missingClassDescription'] = 0
    violations['missingClassDescription'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - All classes have a description annotation.")
    #     if args.verbose:
    #         results = graph.query(class_labels)
    #         print("|  Class | Description |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.c} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['missingClassDescription'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingClassDescription']} classes missing a description annotation:")
        for t in results:
        #   print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['missingClassDescription'] = string
    return metrics, violations, status

def check_property_missing_comment(graph, status):
    """
    QA test counting properties without description.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_missing_comment)
    metrics['missingPropertyDescription'] = 0
    violations['missingPropertyDescription'] = ""
    # if not results and int(metrics['propertyCount']) > 0:
    #     print("PASS - All properties have a description annotation.")
    #     if args.verbose:
    #         results = graph.query(class_labels)
    #         print("| Property | Description |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.p} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No properties defined, invalid metric.")
    # else:
    if results:
        metrics['missingPropertyDescription'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingPropertyDescription']} properties missing a description annotation.")
        for t in results:
        #   print(f" - {t[0]}")
          string += f"{t[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPropertyDescription'] = string
    return metrics, violations, status

def check_node_shape_missing_comment(graph, status):
    """
    QA test counting node shapes without description.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(node_shape_missing_comment)
    metrics['missingNSDescription'] = 0
    violations['missingNSDescription'] = ""
    # if not results and int(metrics['nodeShapes']) > 0:
    #     print("PASS - All NodeShape have a description annotation.")
    #     if args.verbose:
    #         results = graph.query(node_shape_labels)
    #         print("| NodeShape | Description |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.ns} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No NodeShape defined, invalid metric.")
    # else:
    if results:
        metrics['missingNSDescription'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingNSDescription']} NodeShape missing a description annotation:")
        for row in results:
        #  print(f" - {row.ns}")
          string += f"{row.ns},<br> "
        string = string.rstrip(",<br> ")
        violations['missingNSDescription'] = string
    return metrics, violations, status

def check_property_shape_missing_comment(graph, status):
    """
    QA test counting property shapes without description.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_shape_missing_comment)
    metrics['missingPSDescription'] = 0
    violations['missingPSDescription'] = ""
    # if not results and int(metrics['propertyShapes']) > 0:
    #     print("PASS - All PropertyShape have a description annotation.")
    #     if args.verbose:
    #         results = graph.query(property_shape_labels)
    #         print("| PropertyShape | Description |\n|--|--|")
    #         for row in results:
    #             print(f"| {row.ps} | {row.lbl} |")
    # elif not results:
    #     print("WARNING - No PropertyShapes defined, invalid metric.")
    # else:
    if results:
        metrics['missingPSDescription'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['missingPSDescription']} PropertyShape missing a description annotation:")
        for row in results:
        #   print(f" - {row.ps}")
          string += f"{row.ps},<br> "
        string = string.rstrip(",<br> ")
        violations['missingPSDescription'] = string
    return metrics, violations, status

def check_class_same_label(graph, status):
    """
    QA test counting classes sharing the same label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(class_same_label)
    metrics['nonUniqueClassLabels'] = 0
    violations['nonUniqueClassLabels'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - No classes share the same label.")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['nonUniqueClassLabels'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['nonUniqueClassLabels']} labels shared by multiple classes.")
        # print("| Label | Classes |\n|--|--|")
        for row in results:
            # print(f"| {row.label} | {row.classes} |")
            string += f"\"{row.label}\": {row.classes};<br> "
        string = string.rstrip(";<br> ")
        violations['nonUniqueClassLabels'] = string
    return metrics, violations, status

def check_property_same_label(graph, status):
    """
    QA test counting properties sharing the same label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_same_label)
    metrics['nonUniquePropertyLabels'] = 0
    violations['nonUniquePropertyLabels'] = ""
    # if not results and int(metrics['propertyCount']) > 0:
    #     print("PASS - No property share the same label.")
    # elif not results:
    #     print("WARNING - No properties defined, invalid metric.")
    # else:
    if results:
        metrics['nonUniquePropertyLabels'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['nonUniquePropertyLabels']} labels shared by multiple properties.")
        # print("| Label | Properties |\n|--|--|")
        for row in results:
            # print(f"| {row.label} | {row.properties} |")
            string += f"\"{row.label}\": {row.properties};<br> "
        string = string.rstrip(";<br> ")
        violations['nonUniquePropertyLabels'] = string
    return metrics, violations, status

def check_node_shape_same_label(graph, status):
    """
    QA test counting node shapes sharing the same label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(node_shape_same_label)
    metrics['nonUniqueNSLabels'] = 0
    violations['nonUniqueNSLabels'] = ""
    # if not results and int(metrics['nodeShapes']) > 0:
    #     print("PASS - No NodeShape share the same label.")
    # elif not results:
    #     print("WARNING - No NodeShape defined, invalid metric.")
    # else:
    if results:
        metrics['nonUniqueNSLabels'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['nonUniqueNSLabels']} labels shared by multiple NodeShapes.")
        # print("| Label | NodeShapes |\n|--|--|")
        for row in results:
            # print(f"| {row.label} | {row.nsList} |")
            string += f"\"{row.label}\": {row.nsList};<br> "
        string = string.rstrip(";<br> ")
        violations['nonUniqueNSLabels'] = string
    return metrics, violations, status

def check_property_shape_same_label(graph, status):
    """
    QA test counting property shapes sharing the same label.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(property_shape_same_label)
    metrics['nonUniquePSLabels'] = 0
    violations['nonUniquePSLabels'] = ""
    # if not results:
    #     print("PASS - No PropertyShape share the same label.")
    # elif not results:
    #     print("WARNING - No PropertyShapes defined, invalid metric.")
    # else:
    if results:
        metrics['nonUniquePSLabels'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['nonUniquePSLabels']} labels shared by multiple PropertyShapes.")
        # print("| Label | PropertyShapes |\n|--|--|")
        for row in results:
            # print(f"| {row.label} | {row.psList} |")
            string += f"\"{row.label}\": {row.psList};<br> "
        string = string.rstrip(";<br> ")
        violations['nonUniquePSLabels'] = string
    return metrics, violations, status

def check_isolated_classes(graph, status):
    """
    QA test counting classes declared but never used in any other triple connecting them to the rest of the ontology.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(isolated_classes)
    metrics['isolatedClasses'] = 0
    violations['isolatedClasses'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - All classes are connected to another class through a subclass or property relation.")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['isolatedClasses'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['isolatedClasses']} isolated classes:")
        for row in results:
        #   print(f" - {row[0]}")
          string += f"{row[0]},<br> "
        string = string.rstrip(",<br> ")
        violations['isolatedClasses'] = string
    return metrics, violations, status

def check_missing_dr_property(graph, status):
    """
    QA test checking properties for rdfs:domain or rdfs:range declaration.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(missing_dr_property)
    dCount = 0
    rCount = 0
    metrics['missingDomainRange'] = 0
    # if not results and int(metrics['propertyCount']) > 0:
    #     print("PASS - All properties have domain and range defined.")
    # elif not results:
    #     print("WARNING - No properties defined, invalid metric.")
    # else:
    if results:
        metrics['missingDomainRange'] = len(results)
        status += 1
        string = ""
        string2 = ""
        # print(f"VIOLATION - Found {metrics['missingDomainRange']} properties without `rdfs:domain` or `rdfs:range` declaration:")
        # print(f"| Property | Domain | Range |\n| -------- | ------ | ----- |")
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
            # print(f"| {predicate} | {domain} | {prange} |")
    if dCount > 0:
        string = string.rstrip(",<br> ")
        violations['missingDomain'] = string
    else:
        violations['missingDomain'] = ""
    if rCount > 0:
        string2 = string2.rstrip(",<br> ")
        violations['missingRange'] = string2
    else:
        violations['missingRange'] = ""
    metrics['missingDomain'] = dCount
    metrics['missingRange']  = rCount
    return metrics, violations, status

def check_unique_identifiers(graph, status):
    """
    QA test checking for the same resource being declared as semantically inconsistent elements,
    e.g. owl:Class or rdfs:Class and owl:ObjectProperty, rdf:Property owl:DatatypeProperty  owl:AnnotationProperty.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(unique_identifiers)
    # if not results:
    #     print("PASS - No violations found.")
    #     metrics['nonUniqueIdentifiers'] = 0
    #     violations['nonUniqueIdentifiers'] = ""
    # else:
    if results:
        metrics['nonUniqueIdentifiers'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['nonUniqueIdentifiers']} elements with non-unique identifiers.")
        # print("| URI | Declared as |\n|--|--|")
        for row in results:
            # print(f"| {row.iri} | {row.declaredAs} |")
            string += f"{row.iri},<br> "
        string = string.rstrip(",<br> ")
        violations['nonUniqueIdentifiers'] = string
    return metrics, violations, status

def check_subclass_cycles(graph, status):
    """
    QA test counting classes involved in subclass cycles.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(subclass_cycles)
    metrics['subclassCycles'] = 0
    violations['subclassCycles'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - No violations found.")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['subclassCycles'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['subclassCycles']} classes involved in subclass cycles:")
        for row in results:
            # print(f" - {row.c}")
            string += f"{row.c},<br> "
        string = string.rstrip(",<br> ")
        violations['subclassCycles'] = string
    return metrics, violations, status

def check_untyped_class(graph, status):
    """
    QA test counting classes in the current namespace without owl:Class or rdfs:Class declaration
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(untyped_class)
    metrics['untypedClasses'] = 0
    violations['untypedClasses'] = ""
    # if not results and int(metrics['classCount']) > 0:
    #     print("PASS - No violations found.")
    # elif not results:
    #     print("WARNING - No classes defined, invalid metric.")
    # else:
    if results:
        metrics['untypedClasses'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['untypedClasses']} classes without `owl:Class` or `rdfs:Class` declaration:")
        for row in results:
            # print(f" - {row.c}")
            string += f"{row.c},<br> "
        string = string.rstrip(",<br> ")
        violations['untypedClasses'] = string
    # if metrics['ontologyNotDeclared'] == len(metrics['filesProcessed']):
    #   print(f"WARNING - ontology namespace undefined. No way to confirm if the class is defined in the ontology or an external vocabulary.")
    return metrics, violations, status

def check_untyped_property(graph, status):
    """
    QA test counting properties in the current namespace without rdf:Property, owl:ObjectProperty or owl:DatatypeProperty declaration.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(untyped_property)
    metrics['untypedProperties'] = 0
    violations['untypedProperties'] = ""
    # if not results and int(metrics['propertyCount']) > 0:
    #     print("PASS - No violations found.")
    # elif not results:
    #     print("WARNING - No properties defined, invalid metric.")
    # else:
    if results:
        metrics['untypedProperties'] = len(results)
        status += 1
        string = ""
        # print(f"VIOLATION - Found {metrics['untypedProperties']} property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:")
        for row in results:
            # print(f" - {row.p}")
            string += f"{row.p},<br> "
        string = string.rstrip(",<br> ")
        violations['untypedProperties'] = string
    # if qa_metrics['ontologyNotDeclared'] == len(qa_metrics['filesProcessed']):
    #   print(f"WARNING - ontology namespace undefined. No way to confirm if the property is defined in the ontology or an external vocabulary.")
    return metrics, violations, status

def check_hijacking(graph, status):
    """
    QA test counting instances of hijacking, that is, resources defined in the current namespace but using a URI from an external vocabulary.
    
    Args:
        graph (rdflib.Graph): The RDF graph object to parse into.
        status (int): Number of violations before the check.
    
    Returns:
        metrics (dict): Number of violations for various ontology metrics.
        violations (dict): List of elements violating the ontology metrics.
        status (int): Incremental number of violations.
    """
    metrics = {}
    violations = {}
    results = graph.query(hijacking)
    # if not results:
    #     print("PASS - No violations found.") # For now, this condition is never met.
    #     metrics['hijacking'] = 0
    # else:
    if results:
        metrics['hijacking'] = len(results)
        # print(f"VIOLATION - Found {qa_metrics['hijacking']} resources defined using an external vocabulary prefix:")
        # print(f"WARNING - Found resources defined in {metrics['hijacking']} namespaces. Count of entities for each namespace:")
        
        # Add a WARNING if the ontology has not been declared.
        string = ""
        for row in results:
            # print(f" - {row.namespace} {row['count']}")
            el = int(row['count'])
            if el == 1:
                string += f"{row.namespace} ({row['count']} element),<br> "
            elif el > 1:
                string += f"{row.namespace} ({row['count']} elements),<br> "
        string = string.rstrip(",<br> ")
        violations['hijacking'] = string
    return metrics, violations, status

def load_rdf_file(file, graph):
    """
    Load RDF data from a file into the given rdflib Graph.
    
    Args:
        file (str): Path to the RDF file.
        graph (rdflib.Graph): The RDF graph object to parse into.
    
    Returns:
        bool: True if the file was successfully loaded, False otherwise.
        log (str): Parsing result.
    """
    log = f"Loading data from: {file}\n"

    # Try to guess format from file extension
    if file.lower().endswith(('.ttl', '.turtle')):
        fmt = "turtle"
    elif file.lower().endswith(('.rdf', '.owl', '.xml')):
        fmt = "xml"
    else:
        fmt = None  # Let rdflib try to guess
    try:
        graph.parse(file, format=fmt)
        return True, log
    except Exception as e:
        log += f"Failed to parse {file} ({fmt if fmt else 'auto'}): {e}\n"
        return False, log

def load_rdf(f):
    """
    Load RDF files from file or directory name.

    Args:
        f (str): The name of a file or directory.
    
    Returns:
        counter (int): Number of files successfully loaded.
        metrics (dict): Number of violations for various ontology metrics.
        graph (rdflib.Graph): The RDF graph object to parse into.
        log (str): Parsing result.
    """
    counter = 0
    metrics = {}
    metrics['filesProcessed'] = []
    graph = rdflib.Graph()
    log = ""
    # check if f is a directory
    if os.path.isdir(f):
        for root, _, files in os.walk(f):
            for file in files:
                file_path = os.path.join(root, file)
                go, results = load_rdf_file(file_path, graph)
                log += results
                if go:
                  # Append processed file
                  metrics['filesProcessed'].append(file)
                  counter += 1
    else:
        go, results = load_rdf_file(f, graph)
        log += results
        if go:
            # Append processed file
            metrics['filesProcessed'].append(f)
            counter += 1
    return counter, metrics, graph, log

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-e', '--exit-status', action='store_true', help='Report an exit status to determine if one or more violations were detected.')
    parser.add_argument('-v', '--verbose',action='store_true', help='Enable verbose output.')
    parser.add_argument('-p', '--profile-only',action='store_true', help='Compute only the profiling metrics and skip the QA part.')
    parser.add_argument('--ctrf-dir', type=str, metavar='directory', default='ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--ctrf-filename', type=str, metavar='filename', default=None, help='Filename for CTRF report (if None, uses default pattern).')
    parser.add_argument('-o', '--output', type=str, metavar='filename', help='Output file name (optional). If omitted, print to stdout.')
    parser.add_argument('data_files', nargs='+', help='List of RDF files or folders to process.')
    args = parser.parse_args()

    # Create empty dictionaries to store the ontology metrics.
    qa_metrics = {}    # violation count
    qa_violations = {} # violation elements

    # Load Data
    g = rdflib.Graph()
    file_counter = 0
    log_output = "# Ontology Quality Assurance\n\n"
    for f in args.data_files:
        c, file_metrics, file_graph, results = load_rdf(f)
        file_counter += c
        qa_metrics.update(file_metrics)
        g += file_graph
        log_output += results

    if file_counter == 0:
        print(f"{log_output}\nERROR - No RDF data in input files or directories.")
        return
    
    # Compute and store the profiling metrics.
    qa_metrics['triples'] = len(g)
    metrics, violations = profiling(g)
    qa_metrics.update(metrics)
    qa_violations.update(violations)

    # Terminate the execution if further QA checks are not required.
    if args.profile_only:
        log_output += "\n> Profile-only mode enabled. Skipping additional QA checks.\n\n"
        metrics, violations, xs = check_owl_declaration_description(g, len(qa_metrics['filesProcessed']), 0)
        qa_metrics.update(metrics)
        qa_violations.update(violations)
        log_output += print_profiling_metrics(qa_metrics, qa_violations, args.verbose)
        log_output += print_profiling_table(qa_metrics)
        qa_terminate(args.output, log_output)
        return
    
    # Simulate Inference
    g, results = inference(g)
    log_output += results

    # Compute the metrics for Quality Assurance.
    xs = 0  # Number of violations, to decide the exit-status flag.

    # Array with all tests for QA metrics.
    fp = len(qa_metrics['filesProcessed'])
    test_checklist = [
        (True, check_owl_declaration_description,[g,fp], "OWL ontology declaration and description"     ),
        (True, check_class_missing_label,           [g], "Classes missing label annotations"            ),
        (True, check_property_missing_label,        [g], "Properties missing label annotations"         ),
        (True, check_node_shape_missing_label,      [g], "NodeShape missing label annotations"          ),
        (True, check_property_shape_missing_label,  [g], "PropertyShape missing label annotations"      ),
        (True, check_class_missing_comment,         [g], "Classes missing description annotations"      ),
        (True, check_property_missing_comment,      [g], "Properties missing description annotations"   ),
        (True, check_node_shape_missing_comment,    [g], "NodeShape missing description annotations"    ),
        (True, check_property_shape_missing_comment,[g], "PropertyShape missing description annotations"),
        (True, check_class_same_label,              [g], "Classes with the same label"                  ),
        (True, check_property_same_label,           [g], "Properties with the same label"               ),
        (True, check_node_shape_same_label,         [g], "NodeShapes with the same label"               ),
        (True, check_property_shape_same_label,     [g], "PropertyShapes with the same label"           ),
        (True, check_isolated_classes,              [g], "Number of isolated classes"                   ),
        (True, check_missing_dr_property,           [g], "Missing Domain or Range in Properties"        ),
        (True, check_unique_identifiers,            [g], "Non-unique identifiers"                       ),
        (True, check_subclass_cycles,               [g], "Including Cycles in a Class Hierarchy"        ),
        (True, check_untyped_class,                 [g], "Untyped class"                                ),
        (True, check_untyped_property,              [g], "Untyped property"                             ),
        (True, check_hijacking,                     [g], "Namespace hijacking"                          )
    ]

    # TO DO:
    # Parse a configuration file to enable/disable individual tests.

    # Cycle through selected tests.
    for _ in range(len(test_checklist)):
        func = test_checklist[_][1]
        extra_args = test_checklist[_][2]
        if test_checklist[_][0]: metrics, violations, xs = func(*extra_args, xs)

        # Merge returned metrics/violations into global dictionaries
        if metrics:
            qa_metrics.update(metrics)
        if violations:
            qa_violations.update(violations)
    
    # Aggregate and format the results.
    log_output += print_profiling_metrics(qa_metrics, qa_violations, args.verbose)
    log_output += print_qa_results(qa_metrics, qa_violations, test_checklist, args.verbose)

    # Profiling Table
    log_output += print_profiling_table(qa_metrics)

    # QA metrics Table
    log_output += print_qa_table(qa_metrics)

    # Generate CTRF report
    write_ctrf_report(qa_metrics, qa_violations , args.ctrf_dir, args.ctrf_filename)

    # Print the results
    qa_terminate(args.output, log_output)

    # Exit status
    if args.exit_status and xs > 0: sys.exit(1)

# TO DO: Clean this graveyard.

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
