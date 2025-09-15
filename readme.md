# Ontology Quality Assessment

A collection of scripts to assess the quality of ontologies.

`ontology_qa.py` Implements the following QA metrics:

* Missing OWL ontology declaration
* Missing ontology description
* Classes missing label annotation
* Properties missing label annotation
* Classes missing description annotation
* Properties missing description annotation
* Classes with the same label
* Properties with the same label
* Using different naming conventions in the ontology
* Number of isolated classes
* Missing Domain or Range in Properties
* Non-unique identifiers
* No Cycles in a Class Hierarchy
* Untyped class
* Untyped property
* Namespace hijacking

And profiling:

* Number of triples
* Class count
* Property count
* Ontology count
* Average Class Connectivity

