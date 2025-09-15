#!/usr/bin/env python3
# Ontology Quality Assessment Script (v0.1)
# SEMANTIC PARTNERS LTD, 2025
# Authors: Simon Shapiro, Otello M Roscioni.
# Last revision: 2025-09-15

"""
A script to perform basic QA on a set of ontologies.
It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to
check for common ontology quality issues.
It reports any violations found in the ontology data.
"""

import rdflib
import argparse

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
  ?c a ?type .
  FILTER( ?type IN (
    owl:Class,
    rdfs:Class
  ))
  FILTER NOT EXISTS {
    ?sub rdfs:subClassOf ?c .
    ?instance rdf:type ?c .
  }
}
"""

# IA7 Number of Deprecated Classes and Properties
# Count elements marked as deprecated
ia7_deprecated_elements = """
SELECT DISTINCT ?c ?p
WHERE {
  { ?c a owl:DeprecatedClass }
  UNION
  { ?p a owl:DeprecatedProperty }
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
  ?iri a ?type .
  FILTER( ?type IN (
    owl:Class,
    rdfs:Class,
    rdf:Property,
    owl:ObjectProperty,
    owl:DatatypeProperty,
    owl:AnnotationProperty
  ))
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
  ?p a ?ptype .
  FILTER( ?ptype IN (
        rdf:Property,
        owl:ObjectProperty
  ))
  OPTIONAL { ?p rdfs:domain ?d }
  OPTIONAL { ?p rdfs:range  ?r }
  FILTER(BOUND(?d) && BOUND(?r))
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
SELECT ?c (COUNT(?parent) AS ?directAncestors) WHERE {
  ?c rdfs:subClassOf ?parent .
}
GROUP BY ?c
HAVING (COUNT(?parent) > 1)
"""

# ISM1 No OWL ontology declaration
ism1_no_owl_declaration = """
SELECT ?ont WHERE {
  ?ont a owl:Ontology .
}
"""

# No ontology Description
no_ont_description = """
SELECT ?ont WHERE {
  ?ont a owl:Ontology .
  FILTER NOT EXISTS {
    ?ont rdfs:comment|dcterms:abstract|dcterms:description|skos:definition|skos:note ?a .
  }
}
"""

# ISU1 Missing Annotations
# Classes or properties lacking rdfs:label or rdfs:comment
isu1_missing_annotations = """
SELECT DISTINCT ?c ?p WHERE {
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
    print(f"Initial graph size: {len(g)} triples")

    # Count initial classes and properties
    results = g.query(count_cp)
    if not results:
        print("No classes or properties found.")
    else:
        (row,) = results
        print(f"Found {row.classCount} classes and {row.propertyCount} properties.")
        
    print("-" * 20)

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
    elif len(results) == 1:
        (row,) = results
        print(f"PASS - Found 1 ontology with owl:Ontology declaration:\n - {row.ont}")
    elif len(results) > 1:
        print(f"WARNING - Found {len(results)} owl:Ontology declarations:")
        for row in results:
            print(f" - {row.ont}")
    
    print("-" * 20)

    # Missing ontology description.
    if len(results) > 0:
        print("\nRunning check 2: Ontology description.")
        results = g.query(no_ont_description)
        print("")
        if not results:
            print("PASS - All ontologies have a description.")
        else:
            print(f"VIOLATION - Found {len(results)} ontologies without any description:")
            for row in results:
                print(f" - {row.ont}")
    else:
        print("\nSkipping check 2: Ontology description (no ontology declared).")    
    
    print("-" * 20)

    # Missing Annotations
    print("\nRunning check 3: Classes missing label annotations.")
    results = g.query(class_missing_label)
    print("-" * 20)
    
    if not results:
        print("PASS - All classes have a label annotation.")
    else:
        print(f"VIOLATION - Found {len(results)} classes missing a label annotation:")
        for c in results:
          print(f" - {c[0]}")

    print("-" * 20)

    print("\nRunning check 4: Properties missing label annotations.")
    results = g.query(property_missing_label)
    print("-" * 20)

    if not results:
        print("PASS - All properties have a label annotation.")
    else:
        print(f"VIOLATION - Found {len(results)} properties missing a label annotation.")
        for p in results:
          print(f" - {p[0]}")
    
    print("-" * 20)

    print("\nRunning check 5: Classes missing description annotation.")  
    results = g.query(class_missing_comment)
    print("-" * 20)
    
    if not results:
        print("PASS - All classes have a description annotation.")
    else:
        print(f"VIOLATION - Found {len(results)} classes missing a description annotation:")
        for c in results:
          print(f" - {c[0]}")

    print("-" * 20)

    print("\nRunning check 6: Properties missing description annotations.")
    results = g.query(property_missing_comment)
    print("-" * 20)

    if not results:
        print("PASS - All properties have a description annotation.")
    else:
        print(f"VIOLATION - Found {len(results)} properties missing a description annotation.")
        for p in results:
          print(f" - {p[0]}")
    
    print("-" * 20)

    print("\nRunning check 7: Classes with the same label.")
    results = g.query(class_same_label)
    print("-" * 20)
    if not results:
        print("PASS - No classes share the same label.")
    else:
        print(f"VIOLATION - Found {len(results)} labels shared by multiple classes.")
        print(f"- Label\t\tClasses")
        for row in results:
            print(f" - \"{row.label}\"\t{row.classes}")
    
    print("-" * 20)

    print("\nRunning check 8: Properties with the same label.")
    results = g.query(property_same_label)
    print("-" * 20)
    if not results:
        print("PASS - No property share the same label.")
    else:
        print(f"VIOLATION - Found {len(results)} labels shared by multiple properties.")
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
    else:
        print(f"VIOLATION - Found {len(results)} isolated classes:")
        for row in results:
          print(f" - {row[0]}")
            
    print("-" * 20)

    # IC2 Missing Domain or Range in Properties
    print("\nRunning check 10: Missing Domain or Range in Properties:")
    results = g.query(ic2_missing_dr_property)
    print("-" * 20)
    if not results:
        print("PASS - All properties have domain and range defined.")
    else:
        print(f"VIOLATION - Found {len(results)} properties without rdfs:domain or rdfs:range declaration:")
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
    else:
        print(f"VIOLATION - Found {len(results)} elements with non-unique identifiers:")
        for row in results:
            print(f"IRI: {row.iri} - Declared as: {row.declaredAs}")
    
    print("-" * 20)

    # IO2 Including Cycles in a Class Hierarchy
    print("\nRunning check 12: Including Cycles in a Class Hierarchy")
    results = g.query(io2_cycles)
    print("-" * 20)
    if not results:
        print("PASS - No violations found.")
    else:
        print(f"VIOLATION - Found {len(results)} classes involved in subclass cycles:")
        for row in results:
            print(f" - {row.c}")
    
    print("-" * 20)

    # TO DO:
    # Ontology profiling.

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
    
    # IA7 Number of Deprecated Classes and Properties
    #print("\nRunning check for IA7 Number of Deprecated Classes and Properties: count deprecated elements")
    #results = g.query(ia7_deprecated_elements)
    #print("-" * 20)
    #if not results:
    #    print("No IA7 violations found.")
    #else:
    #    print(f"IA7 - Found {len(results.c)} deprecated classes and {len(results.p)} deprecated properties:")
    #    if results.c:
    #        print(f"Deprecated classes:")
    #        for row in results.c:
    #            print(f" - {row}")
    #    if results.p:
    #        print(f"Deprecated properties:")
    #        for row in results.p:
    #            print(f" - {row}")
     
    # print("-" * 20)

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
