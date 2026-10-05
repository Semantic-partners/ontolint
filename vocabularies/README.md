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

| File | Namespace | Source | Version | Licence | Relation to source |
|---|---|---|---|---|---|
| `rdf.ttl` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | <http://www.w3.org/1999/02/22-rdf-syntax-ns> | RDF 1.1 namespace document (2019-12-16), plus RDF 1.2 additions | W3C Software and Document License | The source (retrieved 2026-10-01) verbatim, followed by an 'Added for ontolint' block with the RDF 1.2 terms it does not yet contain: rdf:dirLangString and rdf:reifies (RDF 1.2 Concepts), rdf:PropositionForm and rdf:propositionFormSubject/Predicate/Object (RDF 1.2 Interoperability), and the rdf:version-* IRIs. |
| `rdfs.ttl` | `http://www.w3.org/2000/01/rdf-schema#` | <http://www.w3.org/2000/01/rdf-schema> | not stated (pinned by retrieval date and checksum) | W3C Software and Document License | The source (retrieved 2026-10-01) verbatim, followed by an 'Added for ontolint' block with rdfs:Proposition, the RDF 1.2 term it does not yet contain. |
| `owl.ttl` | `http://www.w3.org/2002/07/owl#` | <http://www.w3.org/2002/07/owl> | 2009-11-15 | W3C Software and Document License | The source (retrieved 2026-10-01) verbatim, followed by an 'Added for ontolint' block with owl:real and owl:rational, the OWL 2 datatypes (OWL 2 Structural Specification section 4.1) it omits. |
| `xsd.ttl` | `http://www.w3.org/2001/XMLSchema#` | <https://www.w3.org/TR/xmlschema11-2/> | XSD 1.1 | MIT, Apache-2.0 | Written for ontolint from XML Schema 1.1 Part 2: Datatypes, as W3C publishes no RDF for XSD: every built-in datatype, the constraining and fundamental facets, and the date/time property names. |
| `shacl.ttl` | `http://www.w3.org/ns/shacl#` | <https://www.w3.org/ns/shacl.ttl> | 2017-07-20 (SHACL 1.0) | W3C Software and Document License | Byte-identical to the source, retrieved 2026-10-01. SHACL 1.2 terms are not included; map the namespace to a newer file via imports.local to use them. |
| `skos.ttl` | `http://www.w3.org/2004/02/skos/core#` | <http://www.w3.org/2004/02/skos/core.rdf> | not stated (pinned by retrieval date and checksum) | W3C Software and Document License | Graph-identical to the source (RDF/XML, retrieved 2026-10-01), as Turtle. |
| `dcterms.ttl` | `http://purl.org/dc/terms/` | <https://www.dublincore.org/specifications/dublin-core/dcmi-terms/dublin_core_terms.ttl> | not stated (pinned by retrieval date and checksum) | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `dc.ttl` | `http://purl.org/dc/elements/1.1/` | <https://www.dublincore.org/specifications/dublin-core/dcmi-terms/dublin_core_elements.ttl> | not stated (pinned by retrieval date and checksum) | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `dcam.ttl` | `http://purl.org/dc/dcam/` | <https://www.dublincore.org/specifications/dublin-core/dcmi-terms/dublin_core_abstract_model.ttl> | not stated (pinned by retrieval date and checksum) | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `dctype.ttl` | `http://purl.org/dc/dcmitype/` | <https://www.dublincore.org/specifications/dublin-core/dcmi-terms/dublin_core_type.ttl> | not stated (pinned by retrieval date and checksum) | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `foaf.ttl` | `http://xmlns.com/foaf/0.1/` | <http://xmlns.com/foaf/spec/index.rdf> | not stated (pinned by retrieval date and checksum) | CC BY 1.0 | Graph-identical to the source (RDF/XML, retrieved 2026-10-01), as Turtle. |
| `vann.ttl` | `http://purl.org/vocab/vann/` | <https://vocab.org/vann/vann-vocab-20100607.rdf> | 2010-06-07 | CC BY 1.0 | Converted to Turtle from the source (RDF/XML, retrieved 2026-10-01), resolving relative IRIs against the source URL. No other changes. |
| `vs.ttl` | `http://www.w3.org/2003/06/sw-vocab-status/ns#` | <http://www.w3.org/2003/06/sw-vocab-status/ns> | not stated (pinned by retrieval date and checksum) | W3C Software and Document License | Graph-identical to the source (RDF/XML, retrieved 2026-10-01), as Turtle. |
| `prov.ttl` | `http://www.w3.org/ns/prov#` | <http://www.w3.org/ns/prov.ttl> | Recommendation 2013-04-30 | W3C Software and Document License | Byte-identical to the source, retrieved 2026-10-01. |
| `org.ttl` | `http://www.w3.org/ns/org#` | <http://www.w3.org/ns/org.ttl> | 0.8 | PDDL 1.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `dcat3.ttl` | `http://www.w3.org/ns/dcat#` | <https://www.w3.org/ns/dcat3.ttl> | 3 | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `vcard.ttl` | `http://www.w3.org/2006/vcard/ns#` | <http://www.w3.org/2006/vcard/ns.ttl> | Final | W3C Software and Document License | Byte-identical to the source, retrieved 2026-10-01. As published by W3C, this includes six terms from the Solid vCard address-book extension (vcard:AddressBook, vcard:WebID, vcard:groupIndex, vcard:inAddressBook, vcard:includesGroup, vcard:nameEmailIndex), marked 'not part of vCard as defined by the IETF'. |
| `schema.ttl` | `http://schema.org/` | <https://schema.org/version/latest/schemaorg-current-http.ttl> | 30.1 | CC BY-SA 3.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `schema-https.ttl` | `https://schema.org/` | <https://schema.org/version/latest/schemaorg-current-https.ttl> | 30.1 | CC BY-SA 3.0 | Byte-identical to the source, retrieved 2026-10-01. |
| `dqv.ttl` | `http://www.w3.org/ns/dqv#` | <https://www.w3.org/ns/dqv.ttl> | W3C Working Group Note 2016-12-15 | W3C Software and Document License | Byte-identical to the source, retrieved 2026-10-05. |
| `time.ttl` | `http://www.w3.org/2006/time#` | <https://www.w3.org/2006/time.ttl> | 2016 (W3C Recommendation 2017-10-19) | CC BY 4.0 | Byte-identical to the source, retrieved 2026-10-05. |
| `odrl.ttl` | `http://www.w3.org/ns/odrl/2/` | <https://www.w3.org/ns/odrl/2/ODRL22.ttl> | 2.2 | W3C Software and Document License | Byte-identical to the source, retrieved 2026-10-05. |
| `dash.ttl` | `http://datashapes.org/dash#` | <https://datashapes.org/dash.ttl> | not stated (pinned by retrieval date and checksum) | Apache-2.0 | Byte-identical to the source, retrieved 2026-10-05. |

Licences are taken from each file's own metadata where it states one. Otherwise they come from the publisher's published terms: the [W3C Software and Document License](https://www.w3.org/copyright/software-license/), DCMI's [CC BY 4.0](https://www.dublincore.org/about/copyright/), FOAF and VANN's CC BY 1.0, TopQuadrant's [Apache-2.0](https://github.com/TopQuadrant/shacl/blob/master/LICENSE) for DASH, and schema.org's [CC BY-SA 3.0](https://schema.org/docs/terms.html). All of these permit redistribution with attribution, which this table provides.

## Provenance

Every file was retrieved on 2026-10-01 (DQV, OWL-Time, ODRL and DASH on 2026-10-05) from the URL in its **Source** column. Its SHA-256 checksum is recorded in the catalog (`spdx:checksum` on its distribution), so the bundle can be checked byte for byte. Most files are byte-identical to their source. The exceptions are listed under **Relation to source**:
- SKOS, FOAF and vocab-status are graph-identical Turtle copies of RDF/XML sources.
- VANN is converted from RDF/XML.
- XSD is written for ontolint.
- RDF, RDFS and OWL are the source text verbatim, followed by a clearly marked "Added for ontolint" block.

## Updating or adding a vocabulary

1. Put the `.ttl` file in this directory and describe it in [`catalog.ttl`](catalog.ttl):
   - a `dcat:Dataset` with `dcterms:title`, `vann:preferredNamespaceUri`, `vann:preferredNamespacePrefix`, `dcterms:source` (the exact URL retrieved), `dcterms:license`, `dcat:version` if the publisher states one, and a `skos:changeNote` saying how the file relates to the source;
   - a `dcat:Distribution` with `dcat:downloadURL <file.ttl>` and an `spdx:checksum` (`spdx:Checksum`, SHA-256 of the file);
   - the dataset listed under the catalog's `dcat:dataset`.
2. Add a row to the table above.
3. Run `poetry run pytest tests/test_vocabularies.py`. The tests check that:
   - every catalog entry exists, parses and defines terms in its namespace;
   - each dataset has its title, source, licence and prefix;
   - each checksum matches its file;
   - the catalog only uses defined terms;
   - this README documents each file;
   - where rdflib has a term list for the vocabulary, the file contains every term on it.
