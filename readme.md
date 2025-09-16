# Ontology Quality Assessment

A collection of scripts to assess the quality of ontologies.

`ontology_qa.py` Implements the following QA metrics:

* Ontology declaration
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

For example, the test ontology [`example.ttl`](tests/example.ttl) returns the following metrics:

| Number of Triples | Class Count | Property Count | Vocabulary Used | Deprecated Classes | Deprecated Properties | Ontology Declared | Ontology Description | Missing Class Label | Missing Property Label | Missing Class Description | Missing Property Description | Non-Unique Class Labels | Non-Unique Property Labels | Isolated Classes | Missing Domain/Range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| 31 | 8 | 4 | 4 | 0 | 0 | 0 | 0 | 4 | 4 | 7 | 4 | 1 | 0 | 2 | 3 | 0 | 0 | 1 | 0 | 1 |

