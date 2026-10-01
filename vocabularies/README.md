# Bundled vocabularies

Standard RDF vocabularies shipped with ontolint so that their terms can be checked **offline**.

[`catalog.ttl`](catalog.ttl) is a [DCAT](https://www.w3.org/TR/vocab-dcat-3/) catalog of these files. Each vocabulary is a `dcat:Dataset` that records:

- its namespace (`vann:preferredNamespaceUri`) and prefix;
- its source (`dcterms:source`), licence (`dcterms:license`), version (`dcat:version`) and local edits (`skos:changeNote`);
- a `dcat:Distribution` whose `dcat:downloadURL` is the bundled file.

ontolint reads the catalog and adds every namespace to `imports.local` automatically. As a result:

- **undefined-terms** checks terms in these namespaces against these files. A typo such as `skos:scopNote` or `xsd:strin` is reported, and no network fetch is made.
- **owl:imports** of these ontologies (e.g. `<http://www.w3.org/2004/02/skos/core>`) resolves from these files.

A project can override any of them with its own `imports.local` entry, or trust a namespace without checking it via `imports.ignore`. See the main [README](../readme.md#bundled-vocabularies).

## Contents

The same information as the catalog, for reading:

| File | Namespace | Source and version | Licence | Local edits |
|---|---|---|---|---|
| `rdf.ttl` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | [RDF namespace document](http://www.w3.org/1999/02/22-rdf-syntax-ns), RDF 1.1 Concepts (2019-12-16) | W3C Software and Document License | **Extended with RDF 1.2 terms** that the published document doesn't yet include: `rdf:dirLangString`, `rdf:reifies` ([RDF 1.2 Concepts](https://www.w3.org/TR/rdf12-concepts/)), `rdf:PropositionForm` and `rdf:propositionFormSubject`/`Predicate`/`Object` ([RDF 1.2 Interoperability](https://www.w3.org/TR/rdf12-interop/)), and the `rdf:version-*` IRIs. Header updated to say so. |
| `rdfs.ttl` | `http://www.w3.org/2000/01/rdf-schema#` | [RDF Schema namespace document](http://www.w3.org/2000/01/rdf-schema) | W3C Software and Document License | None |
| `owl.ttl` | `http://www.w3.org/2002/07/owl#` | [OWL namespace document](http://www.w3.org/2002/07/owl) (2009-11-15) | W3C Software and Document License | **Added `owl:real` and `owl:rational`**, the OWL 2 datatypes from the [OWL 2 Structural Specification §4.1](https://www.w3.org/TR/owl2-syntax/#Datatype_Maps) that the namespace document omits. |
| `xsd.ttl` | `http://www.w3.org/2001/XMLSchema#` | **Written for ontolint** from [XML Schema 1.1 Part 2: Datatypes](https://www.w3.org/TR/xmlschema11-2/). W3C publishes no RDF for XSD. | Same as ontolint (MIT / Apache-2.0) | Not applicable. It lists every built-in datatype (as `rdfs:Datatype`), the constraining and fundamental facets, and the date/time property names. |
| `shacl.ttl` | `http://www.w3.org/ns/shacl#` | [SHACL vocabulary](https://www.w3.org/ns/shacl.ttl), version 2017-07-20 (SHACL 1.0 Recommendation) | W3C Software and Document License (notice in file) | None. SHACL 1.2 terms (e.g. `sh:shape`, `sh:nodeByExpression`, `sh:reifierShape`) are not included yet; map the namespace to a newer file via `imports.local` if you use them. |
| `skos.ttl` | `http://www.w3.org/2004/02/skos/core#` | [SKOS Core](http://www.w3.org/2004/02/skos/core) (SKOS Reference, 2009) | W3C Software and Document License | None |
| `dcterms.ttl` | `http://purl.org/dc/terms/` | [DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) | CC BY 4.0 (DCMI) | None |
| `dc.ttl` | `http://purl.org/dc/elements/1.1/` | [DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) (Dublin Core Elements 1.1) | CC BY 4.0 (DCMI) | None |
| `dcam.ttl` | `http://purl.org/dc/dcam/` | [DCMI Abstract Model terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) | CC BY 4.0 (DCMI) | None |
| `dctype.ttl` | `http://purl.org/dc/dcmitype/` | [DCMI Type Vocabulary](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) | CC BY 4.0 (DCMI) | None |
| `foaf.ttl` | `http://xmlns.com/foaf/0.1/` | [FOAF](http://xmlns.com/foaf/spec/) 0.1 namespace | CC BY 1.0 (FOAF project) | None |
| `vann.ttl` | `http://purl.org/vocab/vann/` | [VANN](https://vocab.org/vann/) | CC BY 1.0, © 2005 Ian Davis (stated in file) | None |
| `vs.ttl` | `http://www.w3.org/2003/06/sw-vocab-status/ns#` | [Vocabulary Status](http://www.w3.org/2003/06/sw-vocab-status/ns) | W3C Software and Document License | None |
| `prov.ttl` | `http://www.w3.org/ns/prov#` | [PROV-O](https://www.w3.org/ns/prov), Recommendation 2013-04-30 | W3C Software and Document License | None |
| `org.ttl` | `http://www.w3.org/ns/org#` | [Organization Ontology](https://www.w3.org/ns/org) 0.8 | PDDL 1.0 (stated in file) | None |
| `dcat3.ttl` | `http://www.w3.org/ns/dcat#` | [DCAT](https://www.w3.org/ns/dcat) version 3 | CC BY 4.0 (stated in file) | None |
| `vcard.ttl` | `http://www.w3.org/2006/vcard/ns#` | [vCard ontology](https://www.w3.org/2006/vcard/ns) | W3C Software and Document License | None |
| `schema.ttl` | `http://schema.org/` | [schema.org](https://schema.org/docs/developers.html) vocabulary, `http` form (version not recorded in the file) | CC BY-SA 3.0 (schema.org) | Removed a comment carried over from another project. |
| `schema-https.ttl` | `https://schema.org/` | Derived from `schema.ttl` by rewriting `http://schema.org/` to `https://schema.org/`, as schema.org publishes both forms | CC BY-SA 3.0 (schema.org) | As `schema.ttl`. |

Licences are taken from each file's own metadata where it states one. Otherwise they come from the publisher's published terms: the [W3C Software and Document License](https://www.w3.org/copyright/software-license/), DCMI's [CC BY 4.0](https://www.dublincore.org/about/copyright/), FOAF and VANN's CC BY 1.0, and schema.org's [CC BY-SA 3.0](https://schema.org/docs/terms.html). All of these permit redistribution with attribution, which this table provides.

## Updating or adding a vocabulary

1. Put the `.ttl` file in this directory and add a `dcat:Dataset` for it to [`catalog.ttl`](catalog.ttl). Give it `dcterms:title`, `vann:preferredNamespaceUri`, `vann:preferredNamespacePrefix`, `dcterms:source`, `dcterms:license`, `dcat:version` if known, and `skos:changeNote` for any local edits. Add a `dcat:Distribution` with `dcat:downloadURL <file.ttl>`, and list the dataset under the catalog's `dcat:dataset`.
2. Add a row to the table above.
3. Run `poetry run pytest tests/test_vocabularies.py`. The tests check that every catalog entry exists, parses and defines terms in its namespace, that each dataset has its title, source, licence and prefix, that the catalog only uses defined terms, and that this README documents each file. Where rdflib has a term list for the vocabulary, they also check the file contains every term on it.
