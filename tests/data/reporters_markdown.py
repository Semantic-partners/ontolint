"""
The Markdown that linting `reporters.ttl` produces, written out as data.

`test_pipeline_lint_to_markdown.py` asserts a lint still renders exactly this. Regenerate
with:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_lint_to_markdown.py

Markdown is not a projection of QAResult yet — the per-check text is rendered inside each
check as it runs — so this is the output of the lint, not of a reporter (see design.md).
When it does become a projection, this file stays as it is and only the way it is produced
changes, which is how the move will be checked.

The report assembled by `main()` wraps this with the heading, the load log and the config
log. Those are run context rather than anything the checks produced, and they carry input
paths, so they are covered by `test_e2e_cli.py` instead.
"""

EXPECTED = """
## Profiling Details

RDF/OWL classes: 8
RDF/OWL properties: 7
Instance data: 1
SHACL Node Shapes: 3
SHACL Property Shapes: 3
Local classes in Node Shapes: 3
Local properties in Property Shapes: 3
Deprecated classes: 1
Deprecated properties: 0
External vocabularies declared: 6

| Prefix | URI |
|--|--|
| dcterms | http://purl.org/dc/terms/ |
| owl | http://www.w3.org/2002/07/owl# |
| rdf | http://www.w3.org/1999/02/22-rdf-syntax-ns# |
| rdfs | http://www.w3.org/2000/01/rdf-schema# |
| sh | http://www.w3.org/ns/shacl# |
| skos | http://www.w3.org/2004/02/skos/core# |

Ontologies imported: 1
* Ontology 'https://example.org/reporters#' imports:
  - https://example.invalid/upstream


Remote namespace resolution: 7 checked
  - ✅ `http://purl.org/dc/terms/` — bundled: `dcterms.ttl`
  - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
  - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
  - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
  - ✅ `http://www.w3.org/2004/02/skos/core#` — bundled: `skos.ttl`
  - ✅ `http://www.w3.org/ns/shacl#` — bundled: `shacl.ttl`
  - ❌ `https://example.invalid/` — fetch failed

Hierarchy depth: N/A
WARNING - The ontology contains cycles in the subclass hierarchy, so the hierarchy depth cannot be computed.
Average branching factor: 2.000
Number of cardinality restrictions: 0

## Quality Assurance Checks

Check 1: Ontology without declaration.
PASS - Found 1 ontology with `owl:Ontology` declaration.

--------------------

Check 2: Ontology without description.
PASS - All declared ontologies have a description.

--------------------

Check 3: Unresolvable imports.
VIOLATION - Found 1 unresolvable or empty import(s):
 - https://example.invalid/upstream

--------------------

Check 4: Undefined terms.
VIOLATION - Found 3 term(s) used but not defined locally or in their vocabulary (bundled, local or fetched):
 - http://www.w3.org/2004/02/skos/core#curatorNote
 - https://example.invalid/upstream (fetch failure)
 - https://example.org/reporters#namingProperty

> **Remote namespace activity** — 7 checked:
>   - ✅ `http://purl.org/dc/terms/` — bundled: `dcterms.ttl`
>   - ✅ `http://www.w3.org/1999/02/22-rdf-syntax-ns#` — bundled: `rdf.ttl`
>   - ✅ `http://www.w3.org/2000/01/rdf-schema#` — bundled: `rdfs.ttl`
>   - ✅ `http://www.w3.org/2002/07/owl#` — bundled: `owl.ttl`
>   - ✅ `http://www.w3.org/2004/02/skos/core#` — bundled: `skos.ttl`
>   - ✅ `http://www.w3.org/ns/shacl#` — bundled: `shacl.ttl`
>   - ❌ `https://example.invalid/` — fetch failed

--------------------

Check 5: Class without label.
VIOLATION - Found 1 classes missing a label annotation:
 - https://example.org/reporters#Cat

--------------------

Check 6: Property without label.
VIOLATION - Found 1 properties missing a label annotation.
 - https://example.org/reporters#undocumented

--------------------

Check 7: NodeShape without label.
VIOLATION - Found 1 NodeShape missing a label annotation.
 - https://example.org/reporters#BareShape

--------------------

Check 8: PropertyShape without label.
VIOLATION - Found 1 PropertyShape missing a label annotation.
 - https://example.org/reporters#bareNameShape

--------------------

Check 9: Class without description.
VIOLATION - Found 2 classes missing a description annotation:
 - https://example.org/reporters#Cat
 - https://example.org/reporters#Dog

--------------------

Check 10: Property without description.
VIOLATION - Found 2 properties missing a description annotation.
 - https://example.org/reporters#hasName
 - https://example.org/reporters#undocumented

--------------------

Check 11: NodeShape without description.
VIOLATION - Found 1 NodeShape missing a description annotation:
 - https://example.org/reporters#BareShape

--------------------

Check 12: PropertyShape without description.
VIOLATION - Found 1 PropertyShape missing a description annotation:
 - https://example.org/reporters#bareNameShape

--------------------

Check 13: Classes with the same label.
VIOLATION - Found 1 labels shared by multiple classes.
| Label | Label Property | Classes |
|--|--|--|
| Dog | http://www.w3.org/2000/01/rdf-schema#label | https://example.org/reporters#Dog, https://example.org/reporters#Hound |

--------------------

Check 14: Properties with the same label.
VIOLATION - Found 1 labels shared by multiple properties.
| Label | Label Property | Properties |
|--|--|--|
| has name | http://www.w3.org/2004/02/skos/core#prefLabel | https://example.org/reporters#alsoHasName, https://example.org/reporters#hasName |

--------------------

Check 15: NodeShapes with the same label.
VIOLATION - Found 1 labels shared by multiple NodeShapes.
| Label | Label Property | NodeShapes |
|--|--|--|
| Animal shape | http://www.w3.org/2000/01/rdf-schema#label | https://example.org/reporters#AnimalShape, https://example.org/reporters#CreatureShape |

--------------------

Check 16: PropertyShapes with the same label.
VIOLATION - Found 1 labels shared by multiple PropertyShapes.
| Label | Label Property | PropertyShapes |
|--|--|--|
| Name shape | http://www.w3.org/2000/01/rdf-schema#label | https://example.org/reporters#animalNameShape, https://example.org/reporters#creatureNameShape |

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
VIOLATION - Found 1 elements with non-unique identifiers.
| URI | Declared as |
|--|--|
| https://example.org/reporters#Ambiguous | owl#Class, owl#ObjectProperty |

--------------------

Check 21: Subclass Cycles.
VIOLATION - Found 2 classes involved in subclass cycles:
 - https://example.org/reporters#Carnivore
 - https://example.org/reporters#Predator

--------------------

Check 22: Untyped Classes.
VIOLATION - Found 1 classes without `owl:Class` or `rdfs:Class` declaration:
 - https://example.org/reporters#Habitat

--------------------

Check 23: Untyped Properties.
VIOLATION - Found 1 property without `rdf:Property`, `owl:ObjectProperty`, or `owl:DatatypeProperty` declaration:
https://example.org/reporters#curatedBy

--------------------

Check 24: Namespace hijacking.
VIOLATION - Found 1 resources defined using an external vocabulary prefix:
 - http://www.w3.org/2004/02/skos/core#curatorNote

--------------------

## Profiling Metrics
| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used | Ontologies Imported | Hierarchy depth | Ave branching factor | Cardinality restrictions |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| https://example.org/reporters# | 94 | 8 | 7 | 3 | 3 | 3 | 3 | 1 | 0 | 6 | 1 | N/A | 2.000 | 0 |

## Quality Assurance Metrics
| Name | Ontology not declared | Ontology without description | Unresolvable Imports | Undefined Terms | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| https://example.org/reporters# | 0 | 0 | 1 | 3 | 0.125 | 0.143 | 0.333 | 0.333 | 0.250 | 0.286 | 0.333 | 0.333 | 0.125 | 0.143 | 0.333 | 0.333 | 0.125 | 0.143 | 0.143 | 1 | 2 | 1 | 1 | 1 |
"""
