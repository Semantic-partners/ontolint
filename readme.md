# Ontology Quality Assessment

A collection of scripts to assess the quality of ontologies.

`ontology_qa.py` Implements the following Profiling metrics:

| Metric Name                                     | Metric Description                                           |
| ----------------------------------------------- | ------------------------------------------------------------ |
| Number of triples                               | Axiom count                                                  |
| Class count                                     | Count number of owl:Class or rdfs:Class                      |
| Property count                                  | Count number of owl:ObjectProperty or rdf:Property           |
| NodeShapes count                                | Count number of sh:NodeShape                                 |
| PropertyShapes count                            | Count number of sh:PropertyShape                             |
| Number of classes specified in NodeShapes       | Number of elements defined as both a (rfds:Class or owl:Class) and sh:NodeShape, or a class defined in sh:NodeShape as the object of sh:targetClass |
| Number of properties specified in PropertyShape | Number of (rdf:Property, owl:ObjectProperty, or owl:DatatypeProperty) defined in sh:PropertyShapes as the object of sh:path |
| Number of Deprecated Classes                    | Elements marked as owl:DeprecatedClass or owl:DeprecatedProperty |
| Number of Deprecated Properties                 | Elements marked as owl:DeprecatedClass or owl:DeprecatedProperty |
| Vocabularies used                               | Number of vocabularies used via a @prefix declaration.       |

And QA metrics:

| Metric Name                                   | Metric Description                                           |
| --------------------------------------------- | ------------------------------------------------------------ |
| Missing ontology declaration                  | No owl:Ontology tag declared                                 |
| Missing ontology description                  | rdfs:comment, dcterms:abstract or dcterms:description predicates not present |
| Classes missing label annotation              | rdfs:label or skos:prefLabel predicates not present          |
| Properties missing label annotation           | rdfs:label or skos:prefLabel predicates not present          |
| NodeShapes missing label annotation           | sh:name, rdfs:label or skos:prefLabel predicates not present |
| PropertyShapes missing label annotation       | sh:name, rdfs:label or skos:prefLabel predicates not present |
| Classes missing description annotation        | rdfs:comment, dcterms:description, or skos:definition predicates not present |
| Properties missing description annotation     | rdfs:comment, dcterms:description, or skos:definition predicates not present |
| NodeShapes missing description annotation     | sh:description, rdfs:comment, dcterms:description, or skos:definition predicates not present |
| PropertyShapes missing description annotation | sh:description, rdfs:comment, dcterms:description, or skos:definition predicates not present |
| Classes with the same label                   | Two or more entities have an identical label annotation in the same language tag. |
| Properties with the same label                | Same as above.                                               |
| NodeShapes with the same label                | Same as above.                                               |
| PropertyShapes with the same label            | Same as above.                                               |
| Number of isolated classes                    | Classes declared but never used in any triple that connects them to the rest of the ontology. |
| Property without domain                       | Property without rdfs:domain declaration.                    |
| Property without range                        | Property without rdfs:range declaration.                     |
| Non-unique identifiers                        | The same identifier is used to define multiple owl:Class, rdfs:Class, rdf:Property, owl:ObjectProperty, owl:DatatypeProperty, or owl:AnnotationProperty. The value refers to the total count. |
| Subclass Cycles                               | Classes involved in a rdfs:subClassOf+ cycle.  The value refers to the total count. |
| Untyped class                                 | An ontology element is used as a class without having been explicitly declared as such using the primitives owl:Class or rdfs:Class. The value refers to the actual number of untyped classes, as they do not apper in the total class count. |
| Untyped property                              | An ontology element is used as a property without having been explicitly declared as such using the primitives rdf:Property, owl:ObjectProperty or owl:DatatypeProperty. The value refers to the actual number of untyped properties, as they do not apper in the total class count. |
| Namespace hijacking                           | Creating a class in the current namespace using the prefix of an external vocabulary. |

For example, the test ontology [`example.ttl`](tests/example.ttl) returns the following results:

#### Profiling Metrics

| Name | Number of Triples | Class Count | Property Count | NodeShapes count | PropertyShapes count | Classes in NodeShapes | Properties in PropertyShape |  Deprecated Classes | Deprecated Properties | Vocabularies Used | 
|--|--|--|--|--|--|--|--|--|--|--|
| tests/example.ttl | 59 | 10 | 5 | 3 | 1 | 7 | 1 | 1 | 0 | 5 |

#### Quality Metrics

| Name | Ontology Declared | Ontology Description | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| tests/example.ttl | no | 0 | 0.600 | 0.800 | 0.333 | 0 | 0.900 | 1.000 | 0.333 | 1.000 | 0.100 | 0 | 0 | 0 | 0.200 | 0.200 | 0.600 | 0 | 0 | 2 | 0 | 1 |

