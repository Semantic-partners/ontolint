# Ontology Linting

[Linting](https://en.wikipedia.org/wiki/Lint_(software)) is the automated analysis of source code to check for coding style or formatting errors. In ontology quality assurance, this process involves defining some quality 

It acts like an automated code review, catching issues like unused variables and improper indentation.

The quality checks focus on completeness, documentation quality, and structural integrity of
the ontologies. The presence of an ontology declaration and a clear ontology description are
essential for attaching metadata such as version, licence, and authorship. The existence of
labels and descriptions across classes, properties, NodeShapes, and PropertyShapes
ensure human-readable annotations that are vital for usability and knowledge sharing.
Additional checks identify duplicate labels, which can create ambiguity, and isolated classes,
which signal weak integration within the ontology. The quality checks assess whether
properties have defined domains and ranges, ensuring they are semantically grounded



Profiling section



## Quality Assurance Tests

### Ontology without declaration

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test verifying that the ontology has a namespace declared as <code>owl:Ontology</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>Without the ontology declaration, other metadata cannot be attached, <i>e.g.</i> label, version, abstract, authors, contributors, licence, and other relevant information.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>owl-declaration</code></dd>
</dl>

### Ontology without description

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test verifying that the ontology has a human-readable description. The annotation is expected to be specified with one of the following predicates: <code>rdfs:comment</code>, <code>dcterms:abstract</code>, <code>dcterms:description</code>, <code>skos:definition</code>, or <code>skos:note</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>An ontology is a repository for knowledge and must contain human-readable documentation, starting from its own description. This test implies the one on ontology declaration is also enabled.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>owl-description </code></dd>
</dl>

### Unresolvable imports

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test verifying that all <code>owl:imports</code> URLs resolve and contain triples.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>Resolving imported ontologies and vocabularies enables modular design and semantic consistency. This test implies the one on ontology declaration is also enabled.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>owl-imports</code></dd>
</dl>

### Undefined terms

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test finding terms used in the ontology that are not defined locally (as a subject in the graph file) nor in any successfully-fetched remote ontology for their namespace.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>An undefined term is an RDF resource which has been used in a triple but never as the subject in the local namespace. Alternatively, it is a resource declared in an external namespace but not present in it. This test overlaps with <b>namespace hijacking</b>, <b>untyped classes</b>, and <b>untyped properties</b>. While these other tests are more granular and rely on a SPARQL query to identify any violation, this test explicitly control that a given resource is present in the corresponding external ontology or vocabulary.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>undefined-terms</code></dd>
</dl>

### Class without label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes without a label. The label must be declared using one of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>class-missing-label</code></dd>
</dl>rdfs:label|skos:prefLabel|skos:altLabel|skos:hiddenLabel

### Property without label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting properties without a label. The label must be declared using one of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-missing-label</code></dd>
</dl>

### NodeShape without label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting node shapes without a label. The label must be declared using one of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>node-shape-missing-label</code></dd>
</dl>

### PropertyShape without label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting property shapes without a label. The label must be declared using one of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-shape-missing-label</code></dd>
</dl>

### Class without description

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes without description. The description must be declared using one of the following predicates: <code>rdfs:comment</code>, <code>dcterms:description</code>, or <code>skos:definition</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>class-missing-comment</code></dd>
</dl>

### Property without description

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting properties without description. The description must be declared using one of the following predicates: <code>rdfs:comment</code>, <code>dcterms:description</code>, or <code>skos:definition</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-missing-comment</code></dd>
</dl>

### NodeShape without description

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting node shapes without description. The description must be declared using one of the following predicates: <code>rdfs:comment</code>, <code>dcterms:description</code>, or <code>skos:definition</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>node-shape-missing-comment</code></dd>
</dl>

### PropertyShape without description

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting property shapes without description. The description must be declared using one of the following predicates: <code>rdfs:comment</code>, <code>dcterms:description</code>, or <code>skos:definition</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>All entities in an ontology should have human-readable annotations for documentation purposes.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-shape-missing-comment</code></dd>
</dl>

### Classes with the same label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes sharing the same label. The label may be declared with any of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>To ensure high-quality documentation within a given namespace
(<i>e.g.</i> a domain ontology), every entity must have a unique,
human-readable label to prevent ambiguous definitions. Multiple labels can be declared, but they should only have one value per
language tag.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>class-same-label</code></dd>
</dl>

### Properties with the same label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting properties sharing the same label. The label may be declared with any of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>To ensure high-quality documentation within a given namespace
(<i>e.g.</i> a domain ontology), every entity must have a unique,
human-readable label to prevent ambiguous definitions. Multiple labels can be declared, but they should only have one value per
language tag.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-same-label</code></dd>
</dl>

### NodeShapes with the same label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting node shapes sharing the same label. The label may be declared with any of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>To ensure high-quality documentation within a given namespace
(<i>e.g.</i> a domain ontology), every entity must have a unique,
human-readable label to prevent ambiguous definitions. Multiple labels can be declared, but they should only have one value per
language tag.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>node-shape-same-label</code></dd>
</dl>

### PropertyShapes with the same label

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting property shapes sharing the same label. The label may be declared with any of the following predicates: <code>rdfs:label</code>, <code>skos:prefLabel</code>, <code>skos:altLabel</code>, or <code>skos:hiddenLabel</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>To ensure high-quality documentation within a given namespace
(<i>e.g.</i> a domain ontology), every entity must have a unique,
human-readable label to prevent ambiguous definitions. Multiple labels can be declared, but they should only have one value per
language tag.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-shape-same-label</code></dd>
</dl>

### Isolated classes 

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes declared but never used in any other triple connecting them to the rest of the ontology.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>Ensure that every declared class has sufficiently detailed
specifications, i.e. it must be connected to the rest of the ontology
with at least one of the predicates: <code>rdfs:subClassOf</code>, <code>rdfs:domain</code>, <code>rdfs:range</code>, <code>sh:class</code>, or <code>sh:targetClass</code>.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>isolated-classes</code></dd>
</dl>

### Property without domain

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test checking properties without <code>rdfs:domain</code> declaration.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>This test is only relevant if the design principles require properties to be restricted to a certain domain.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-missing-domain</code></dd>
</dl>

### Property without range

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test checking properties without <code>rdfs:range</code> declaration.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>This test is only relevant if the design principles require properties to be restricted to a certain range.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>property-missing-range</code></dd>
</dl>

### Non-unique identifiers

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test checking for the same resource being declared as semantically inconsistent elements, <i>e.g.</i> <code>owl:Class</code> or <code>rdfs:Class</code> and <code>owl:ObjectProperty</code>, <code>rdf:Property</code>, <code>owl:DatatypeProperty</code>, </code>owl:AnnotationProperty</code>.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>The same identifier (URI) should not be used for both a Class and Property.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>unique-identifiers</code></dd>
</dl>

### Subclass Cycles

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes involved in <code>rdfs:subClassOf+</code>  cycles.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd>It is a logical inconsistency that may occur if a chain of <code>rdfs:subClassOf</code> relations eventually lands on the same class it originated from. This error may go unnoticed, especially in a large ontology.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>subclass-cycles</code></dd>
</dl>

### Untyped Classes

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd>QA test counting classes in the current namespace without <code>owl:Class</code> or <code>rdfs:Class</code> declaration.</dd>
  <dt><strong>Rationale</strong></dt>
  <dd></dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>untyped-class</code></dd>
</dl>

### Untyped Properties

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd></dd>
  <dt><strong>Rationale</strong></dt>
  <dd></dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>untyped-property</code></dd>
</dl>
### Namespace hijacking

<dl>
  <dt><strong>Metric Description</strong></dt>
  <dd></dd>
  <dt><strong>Rationale</strong></dt>
  <dd>the current version of namespace hijacking is designed to be very strict, basically flagging any external resource used as a subject of a triple. For example, the triple <code>skos:Concept a owl:Class</code> will be reported as namespace hijacking, despite being a perfectly valid (although unnecessary) statement.</dd>
  <dt><strong>Lint keyword</strong></dt>
  <dd><code>hijacking</code></dd>
</dl>
