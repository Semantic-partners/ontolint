
## Profiling Details

RDF/OWL classes: 2
RDF/OWL properties: 1
Instance data: 0
SHACL Node Shapes: 0
SHACL Property Shapes: 0
Local classes in Node Shapes: 0
Local properties in Property Shapes: 0
Deprecated classes: 0
Deprecated properties: 0
External vocabularies declared: 4

| Prefix | URI |
|--|--|
| frag | https://example.org/fragment# |
| owl | http://www.w3.org/2002/07/owl# |
| rdf | http://www.w3.org/1999/02/22-rdf-syntax-ns# |
| rdfs | http://www.w3.org/2000/01/rdf-schema# |

Ontologies imported: 0

Remote namespace resolution: 4 checked
  - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
  - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
  - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
  - ❌ `https://example.org/fragment#` — fetch failed

Hierarchy depth: 0
Average branching factor: 0
Number of cardinality restrictions: 0

## Quality Assurance Checks

Check 1: Ontology without declaration.
VIOLATION - No `owl:Ontology` declaration found.
Check the input files individually to find out which one violates this check.

--------------------

Check 2: Multiple ontologies in one file.
PASS - No violations found.

--------------------

Check 3: Ontology without description.
WARNING - No ontology declared, invalid metric.

--------------------

Check 4: Unresolvable imports.
WARNING - No owl:imports statements found.

--------------------

Check 5: Undefined terms.
VIOLATION - Found 3 term(s) used but not defined locally or in their vocabulary (bundled, local or fetched):
 - https://example.org/fragment#Tool (fetch failure)
 - https://example.org/fragment#Worker (fetch failure)
 - https://example.org/fragment#usedBy (fetch failure)

> **Remote namespace activity** — 4 checked:
>   - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
>   - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
>   - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
>   - ❌ `https://example.org/fragment#` — fetch failed

WARNING - No owl:Ontology declared; local namespace is unknown. Local dangling references may not be detected.

--------------------

Check 6: Class without label.
PASS - All classes have a label annotation.

--------------------

Check 7: Property without label.
PASS - All properties have a label annotation.

--------------------

Check 8: NodeShape without label.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 9: PropertyShape without label.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 10: Class without description.
PASS - All classes have a description annotation.

--------------------

Check 11: Property without description.
PASS - All properties have a description annotation.

--------------------

Check 12: NodeShape without description.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 13: PropertyShape without description.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 14: Classes with the same label.
PASS - No classes share the same label.

--------------------

Check 15: Properties with the same label.
PASS - No property share the same label.

--------------------

Check 16: NodeShapes with the same label.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 17: PropertyShapes with the same label.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 18: Isolated classes.
PASS - All classes are connected to another class through a subclass or property relation.

--------------------

Check 19: Property without domain.
INFO - All properties have domain and range defined.
PASS - All properties have domain defined.

--------------------

Check 20: Property without range.
PASS - All properties have range defined.

--------------------

Check 21: Non-unique identifiers.
PASS - No violations found.

--------------------

Check 22: Subclass Cycles.
PASS - No violations found.

--------------------

Check 23: Untyped Classes.
WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a class is defined in the ontology or an external vocabulary.

--------------------

Check 24: Untyped Properties.
WARNING - Ontology namespace undefined, invalid metric. No way to confirm if a property is defined in the ontology or an external vocabulary.

--------------------

Check 25: Namespace hijacking.
PASS - No violations found.
WARNING - Ontology namespace undefined. The reported violations may be incorrect.

--------------------

## Profiling Metrics
| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported | Hierarchy depth | Ave branching factor | Cardinality restrictions |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| fragment.ttl | 11 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |

## Quality Assurance Metrics
| Name | Ontology not declared | Multiple ontologies in one file | Ontology without description | Unresolvable Imports | Undefined Terms | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| fragment.ttl | 1 | 0 | 1 | 0 | 3 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
