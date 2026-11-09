# Configuring Ontolint

A run is configured by a `.rdf-lint.yml` file. The command line reads `.rdf-lint.yml` from
the working directory when there is one, or the file named by `-c`; the GitHub Action reads
it from the repository root, or from `config-path`. `ontolint --init` writes a starter file
listing every check. The Python API takes the same settings as a `Config` — see
[the API](python-api.md#config).

Every key is optional. With no file, every check runs with the defaults below.

## Choosing checks

```yaml
# Run only these checks. Leave the key out to run all of them.
enable:
  - owl-description
  - class-missing-label

# Or run all of them except these.
disable:
  - property-missing-domain
  - property-missing-range
```

Leaving `enable` out runs every check, and so does an `enable:` with nothing under it,
which YAML reads as null. An explicit empty list, `enable: []`, runs **none** — and a run
with no checks passes, even with `-e`.

Checks are named as in the [check list](../readme.md#checks). A check that another one
needs is turned back on, and the report says why: `owl-description`, for example, needs
`owl-declaration`, and so does `undefined-terms`, to tell the ontology's own namespace from
one it has to resolve.

## Excluding resources by type

Some encodings introduce resources that aren't real ontology terms. For example, when an
RDF 1.2 ontology is downgraded to RDF 1.1, each triple term becomes an `rdf:PropositionForm`
stand-in in the ontology's own namespace, and these would otherwise be flagged as untyped
classes. List such types under `exclude.types` to skip their instances in the class checks
(`class-missing-label`, `class-missing-comment`, `class-same-label`, `isolated-classes`,
`untyped-class`). All other resources are still checked:

```yaml
exclude:
  types:
    - rdf:PropositionForm
```

Entries can be full IRIs or compact IRIs using the `rdf:`, `rdfs:`, `owl:`, `xsd:`,
`skos:`, `sh:`, `dcterms:`, `foaf:`, `schema:` or `vs:` prefixes.

## Reference properties in the undefined-terms check

The undefined-terms check skips the objects of reference and documentation properties.
Those objects are links to documents (a Wikipedia page, a licence), not ontology terms, so
they are neither reported nor fetched. The same IRI used as a real term, as a subject or as
the object of any other property, is still checked. The default properties are:

`rdfs:seeAlso`, `rdfs:isDefinedBy`, `dcterms:license`, `dcterms:source`,
`dcterms:references`, `dcterms:relation`, `dcterms:conformsTo`, `owl:versionIRI`,
`foaf:homepage`, `foaf:page`, `vs:*` (any
[vocab-status](http://www.w3.org/2003/06/sw-vocab-status/ns#) property) and `schema:url`
(both `https://` and `http://` schema.org).

To use your own list, set `undefined-terms.skip-object-of`. It **replaces** the defaults,
`prefix:*` matches a whole namespace, and an empty list checks every object:

```yaml
undefined-terms:
  skip-object-of:
    - rdfs:seeAlso
    - dcterms:license
    - https://example.org/ns#docs
```

You don't need `imports.ignore` entries for `rdfs:seeAlso`, licence or source links; keep
`imports.ignore` for importable namespaces you choose not to resolve.

## Resolving namespaces and imports

Two checks look outside the ontology: `undefined-terms` looks each used term up in its
namespace's vocabulary, and `owl-imports` resolves each `owl:imports`. Where a vocabulary
comes from is decided, in order of precedence, by:

1. `imports.local` — a file you name;
2. another input of the same run (`imports.siblings`);
3. the vocabularies bundled with ontolint;
4. the network.

```yaml
imports:
  # Trusted: never fetched, and its terms are never reported (undefined-terms);
  # owl:imports of it are not resolved (owl-imports).
  ignore:
    - http://example.org/vendor/ns#
  # Resolve a namespace / import from a local file instead of the network. An entry here
  # takes precedence over the bundled copy, e.g. to use a newer SHACL vocabulary.
  local:
    http://www.w3.org/ns/shacl#: vocab/shacl-1.2.ttl
    https://example.org/partner/ontology: vocab/partner.ttl
  # Resolve references against the other inputs of the same run. On unless set to false.
  siblings: true
```

Entries match **with or without a trailing `#` or `/`**, so
`http://www.w3.org/2004/02/skos/core` and `http://www.w3.org/2004/02/skos/core#` are the
same entry. One entry covers both the namespace (used by undefined-terms) and the ontology
IRI (used by owl-imports). Relative `local` paths are resolved from the config file's
directory.

### Bundled vocabularies

Ontolint ships copies of the standard vocabularies: RDF (with the RDF 1.2 terms), RDFS, OWL,
XSD, SHACL, SKOS, Dublin Core (`dcterms`, `dc`, `dcam`, `dctype`), FOAF, VANN, Vocabulary
Status, PROV, ORG, DCAT 3, DQV, OWL-Time, ODRL, DASH, vCard and schema.org (both `http://`
and `https://`). They are used automatically, with no config:

- **Typos are caught, offline.** The undefined-terms check validates terms in these
  namespaces against the bundled files instead of trusting them. `skos:scopNote`,
  `dcterms:licence` and `xsd:strin` are reported. `skos:scopeNote`, `rdf:reifies`,
  `rdf:PropositionForm` and `xsd:dateTimeStamp` are not. Nothing is fetched for these
  namespaces, and `rdf:_1`, `rdf:_2`, … are always accepted.
- **`owl:imports` of these ontologies resolves locally,** e.g.
  `owl:imports <http://www.w3.org/2004/02/skos/core>`.

The run log shows which namespaces were resolved from the bundle (`bundled: skos.ttl`) and
which were fetched. Sources, versions, licences and local edits are listed in
[`src/ontolint/vocabularies/README.md`](../src/ontolint/vocabularies/README.md).

To trust one of these namespaces without checking its terms, list it under
`imports.ignore`.

### `imports.siblings` — resolving against the rest of the run

A family of ontologies usually refers to itself long before any of it is published. Rather
than making you list each member under `local`, ontolint resolves a reference against **the
other inputs of the same invocation**:

```
Check 5: Undefined terms.
PASS - All used terms are defined locally or in their respective remote ontologies.

>   - ✅ `https://example.org/core#` — another input: `./core.ttl`
```

Three things are worth knowing:

- **An input answers only for the ontology it declares**, not for every namespace it has
  subjects in. Otherwise a file that mints a term in someone else's namespace would shadow
  that vocabulary for every file beside it.
- **An input resolves only for the runs it is not part of.** Linting one file on its own has
  no siblings, so a reference to a file outside that run still needs a `local` entry.
- **Precedence** is bundled < another input of the run < `local`, which stays an explicit
  instruction.

Every ontology resolved this way is named in the DQV report's `olq:Configuration`, with
`olq:origin olq:RunInput` and the input it came from, so it is explicit what answered for
what. Turn it off with `siblings: false` — a project linting a directory of unrelated
ontologies may want each judged strictly alone.
