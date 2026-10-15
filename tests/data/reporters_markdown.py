"""
The Markdown that linting `reporters.ttl` produces, written out as data.

`test_lint_to_markdown.py` asserts a lint still renders exactly this. It is stored the same
way as the QAResult beside it, for the same reason: when the rendering changes on purpose
the diff is reviewable, and when it changes by accident the test says so.

Markdown is not a projection of QAResult yet — the per-check text is rendered inside each
check as it runs — so this is the output of the lint, not of a reporter (see design.md).
When it does become a projection, this file stays as it is and only the way it is produced
changes, which is how the move will be checked.

The report assembled by `main()` wraps this with the heading, the load log and the config
log. Those are run context rather than anything the checks produced, and they carry input
paths, so they are covered by `test_integration.py` instead.
"""

EXPECTED = """
## Profiling Details

RDF/OWL classes: 5
RDF/OWL properties: 2
Instance data: 1
SHACL Node Shapes: 0
SHACL Property Shapes: 0
Local classes in Node Shapes: 0
Local properties in Property Shapes: 0
Deprecated classes: 1
Deprecated properties: 0
External vocabularies declared: 5

| Prefix | URI |
|--|--|
| dcterms | http://purl.org/dc/terms/ |
| owl | http://www.w3.org/2002/07/owl# |
| rdf | http://www.w3.org/1999/02/22-rdf-syntax-ns# |
| rdfs | http://www.w3.org/2000/01/rdf-schema# |
| skos | http://www.w3.org/2004/02/skos/core# |

Ontologies imported: 0

Remote namespace resolution: 5 checked
  - ✅ `http://purl.org/dc/terms/` — bundled: `dcterms.ttl`
  - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
  - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
  - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
  - ✅ `http://www.w3.org/2004/02/skos/core#` — bundled: `skos.ttl`

Hierarchy depth: 1
Average branching factor: 3.000
Number of cardinality restrictions: 0

## Quality Assurance Checks

Check 1: Ontology without declaration.
PASS - Found 1 ontology with `owl:Ontology` declaration.

--------------------

Check 2: Ontology without description.
PASS - All declared ontologies have a description.

--------------------

Check 3: Unresolvable imports.
WARNING - No owl:imports statements found.

--------------------

Check 4: Undefined terms.
PASS - All used terms are defined locally or in their respective remote ontologies.

> **Remote namespace activity** — 5 checked:
>   - ✅ `http://purl.org/dc/terms/` — bundled: `dcterms.ttl`
>   - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
>   - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
>   - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
>   - ✅ `http://www.w3.org/2004/02/skos/core#` — bundled: `skos.ttl`

--------------------

Check 5: Class without label.
VIOLATION - Found 1 classes missing a label annotation:
 - https://example.org/reporters#Cat

--------------------

Check 6: Property without label.
PASS - All properties have a label annotation.

--------------------

Check 7: NodeShape without label.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 8: PropertyShape without label.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 9: Class without description.
VIOLATION - Found 2 classes missing a description annotation:
 - https://example.org/reporters#Cat
 - https://example.org/reporters#Dog

--------------------

Check 10: Property without description.
VIOLATION - Found 1 properties missing a description annotation.
 - https://example.org/reporters#hasName

--------------------

Check 11: NodeShape without description.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 12: PropertyShape without description.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 13: Classes with the same label.
VIOLATION - Found 1 labels shared by multiple classes.
| Label | Label Property | Classes |
|--|--|--|
| Dog | http://www.w3.org/2000/01/rdf-schema#label | https://example.org/reporters#Dog, https://example.org/reporters#Hound |

--------------------

Check 14: Properties with the same label.
PASS - No property share the same label.

--------------------

Check 15: NodeShapes with the same label.
WARNING - No NodeShape defined, invalid metric.

--------------------

Check 16: PropertyShapes with the same label.
WARNING - No PropertyShapes defined, invalid metric.

--------------------

Check 17: Isolated classes.
VIOLATION - Found 1 isolated classes:
 - https://example.org/reporters#Mineral

--------------------

Check 18: Missing Domain in Properties.
WARNING - Found 1 properties without `rdfs:domain` or `rdfs:range` declaration:

| Property | Domain | Range |
|--|--|--|
| https://example.org/reporters#hasName | None | None |

VIOLATION - Found 1 properties without `rdfs:domain` declaration:
 - https://example.org/reporters#hasName

--------------------

Check 19: Missing Range in Properties.
VIOLATION - Found 1 properties without `rdfs:range` declaration:
 - https://example.org/reporters#hasName

--------------------

Check 20: Non-unique identifiers.
PASS - No violations found.

--------------------

Check 21: Subclass Cycles.
PASS - No violations found.

--------------------

Check 22: Untyped Classes.
PASS - No violations found.

--------------------

Check 23: Untyped Properties.
PASS - No violations found.

--------------------

Check 24: Namespace hijacking.
PASS - No violations found.

--------------------

## Profiling Metrics
| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported | Hierarchy depth | Ave branching factor | Cardinality restrictions |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| https://example.org/reporters# | 35 | 5 | 2 | 0 | 0 | 0 | 0 | 1 | 0 | 5 | 0 | 1 | 3.000 | 0 |

## Quality Assurance Metrics
| Name | Ontology not declared | Ontology without description | Unresolvable Imports | Undefined Terms | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| https://example.org/reporters# | 0 | 0 | 0 | 0 | 0.200 | 0 | 1 | 1 | 0.400 | 0.500 | 1 | 1 | 0.200 | 0 | 1 | 1 | 0.200 | 0.500 | 0.500 | 0 | 0 | 0 | 0 | 0 |
"""
