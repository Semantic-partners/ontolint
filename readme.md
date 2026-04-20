# Ontolint: Ontology Quality Assessment

Get an instant, user-friendly snapshot of your ontology’s size and health, right in your CI pipeline. This tool profiles your ontology file (triples, classes, properties, etc.) and runs quality checks (declarations, descriptions, versioning, structure), then produces a clear report so you can track complexity over time, catch regressions early, and keep your ontology consistently high-quality.

## Usage

We have a [Github workflow](/.github/workflows/ci-test.yml) running against an [example ontology](/tests/example.ttl) - use this as a reference.

The `ontology_qa.py` script performs quality assurance on a set of ontologies. It loads RDF files, applies simple RDFS subclass inference, and runs SPARQL queries to check for common ontology quality issues. It reports any violations found in the ontology data

```bash
usage: ontology_qa.py [-h] [-e] [-v] [-p] [--ctrf-dir CTRF_DIR] [--ctrf-filename CTRF_FILENAME] data_files [data_files ...]

positional arguments:
  data_files            List of RDF files or folders to process.

optional arguments:
  -h, --help            show this help message and exit
  -e, --exit-status     Report an exit status to determine if one or more violations were detected.
  -v, --verbose         Enable verbose output.
  -p, --profile-only    Compute only the profiling metrics and skip the QA part.
  --ctrf-dir CTRF_DIR   Directory to write CTRF report to.
  --ctrf-filename CTRF_FILENAME
                        Filename for CTRF report (if None, uses default pattern).
```

The `generate_custom_report.py` script generates a custom markdown report from aggregated CTRF JSON files. Uses Handlebars template to render the report.

```bash
usage: generate_custom_report.py [-h] [--ctrf-dir directory] [--template-path directory] [--output-path directory]

optional arguments:
  -h, --help            show this help message and exit
  --ctrf-dir directory  Directory to write CTRF report to.
  --template-path directory
                        Path to the CTRF report template file.
  --output-path directory
                        Path to write the CTRF markdown report file.
```

## Dev setup
Install poetry with the [instructions here](https://python-poetry.org/docs/#installation), or `brew install poetry` if you're on mac with homebrew.

To test the script works, run the script using the example file:
```poetry run scripts/ontology_qa.py tests/example.ttl```

It should generate a JSON files in the ctrf directory.

## New features

The backlog is managed in a [GitHub project](https://github.com/orgs/Semantic-partners/projects/3).

## Implementation

A collection of SPARQL queries to assess the quality of ontologies and executed with RDFLib. The script `ontology_qa.py` first creates a graph loading one or more ontologies. For quality assessment, one ontology at a time should be processed. The output is printed to the standard output in the markdown format.

`ontology_qa.py` Implements the following Profiling metrics:

| Metric Name                                   | Metric Description                                           |
| --------------------------------------------- | ------------------------------------------------------------ |
| Number of triples                             | Axiom count                                                  |
| Class count                                   | Count number of owl:Class or rdfs:Class                      |
| Property count                                | Count number of owl:ObjectProperty or rdf:Property           |
| NodeShape count                               | Count number of sh:NodeShape                                 |
| PropertyShape count                           | Count number of sh:PropertyShape                             |
| Local classes constrained in NodeShapes       | Number of elements defined as both a (rdfs:Class or owl:Class) and sh:NodeShape, or a class defined in sh:NodeShape as the object of sh:targetClass |
| Local properties constrained in PropertyShape | Number of (rdf:Property, owl:ObjectProperty, or owl:DatatypeProperty) defined in sh:PropertyShapes as the object of sh:path |
| Number of deprecated classes                  | Elements marked as owl:DeprecatedClass                       |
| Number of deprecated properties               | Elements marked as owl:DeprecatedProperty                    |
| Vocabularies used                             | Number of vocabularies used via a @prefix declaration        |

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
| Classes with the same label                   | Two or more entities have an identical label annotation in the same language tag |
| Properties with the same label                | Same as above.                                               |
| NodeShapes with the same label                | Same as above.                                               |
| PropertyShapes with the same label            | Same as above.                                               |
| Number of isolated classes                    | Classes declared but never used in any triple that connects them to the rest of the ontology. |
| Property without domain                       | Property without rdfs:domain declaration.                    |
| Property without range                        | Property without rdfs:range declaration.                     |
| Non-unique identifiers                        | The same identifier is used to define multiple owl:Class, rdfs:Class, rdf:Property, owl:ObjectProperty, owl:DatatypeProperty, or owl:AnnotationProperty. The value refers to the total count. |
| Subclass cycles                               | Classes involved in a rdfs:subClassOf+ cycle.  The value refers to the total count. |
| Untyped class                                 | An ontology element is used as a class without having been explicitly declared as such using the primitives owl:Class or rdfs:Class. The value refers to the actual number of untyped classes, as they do not appear in the total class count. |
| Untyped property                              | An ontology element is used as a property without having been explicitly declared as such using the primitives rdf:Property, owl:ObjectProperty or owl:DatatypeProperty. The value refers to the actual number of untyped properties, as they do not appear in the total class count. |
| Namespace hijacking                           | Creating a class in the current namespace using the prefix of an external vocabulary. The script reports the count of subjects sorted by namespace. The user should then verify that the subjects are defined in the external ontology and not minted *ex-novo*. |

For example, the test ontology [`example.ttl`](tests/example.ttl) returns the following results:

### Profiling Metrics

| Name | Number of triples | Class count | Property count | NodeShape count | PropertyShape count | Local classes in NodeShape | Local properties in PropertyShape | Deprecated Class count | Deprecated Property count | Vocabularies used |
|--|--|--|--|--|--|--|--|--|--|--|
| http://my.ont.example# | 65 | 11 | 5 | 3 | 1 | 7 | 1 | 1 | 0 | 5 |

### Quality Metrics

| Name | Ontology not declared | Ontology without description | Class without label | Property without label | NodeShapes without label | PropertyShape without label | Class without description | Property without description | NodeShapes without description | PropertyShape without description | Non-Unique Class Labels | Non-Unique Property Labels | Non-Unique NodeShape Labels | Non-Unique PropertyShape Labels | Isolated Classes | Property without domain | Property without range | Non-Unique Identifiers | Subclass Cycles | Untyped Classes | Untyped Properties | Namespace hijacking |
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| http://my.ont.example# | 0 | 0 | 0.636 | 0.800 | 0.333 | 0 | 0.909 | 1 | 0.333 | 1 | 0.091 | 0 | 0 | 0 | 0.273 | 0.200 | 0.600 | 1 | 0 | 2 | 0 | 1 |

### Batch Processing

For quality assessment, one ontology at a time should be processed. The following script runs `ontology_qa.py` and then uses `grep` to collect the output to two markdown tables.

```bash
#!/bin/bash

# Script path
sp=path/to/ontolint/scripts

# Run the QA metric script, save the results and grep the Profiling table.
for ont in *.ttl
do
 python3 $sp/ontology_qa.py $ont > ${ont%.ttl}.out
 grep -A 1 -e "|--|--|" ${ont%.ttl}.out | grep -v -e "--" | head -1 >> ont_tables.md
done

# Grep the QA metrics table.
echo "" >> ont_tables.md
for ont in *.ttl
do
 grep -A 1 -e "|--|--|" ${ont%.ttl}.out | grep -v -e "--" | tail -1 >> ont_tables.md
done
```
## GitHub Actions

To deploy the QA script on a different repository, create the following folder in the root of the repository: `.github/workflows` and adapt the example in [`ci-example.yml`](.github/workflows/ci-example.yml). The workflow will need to be adapted in the following sections:

```yaml
    steps:
      - name: Check out the current repository
        uses: actions/checkout@v5

      # Updated with token
      - name: Check out ontology QA repository
        uses: actions/checkout@v5
        with:
          repository: Semantic-partners/ontolint
          ref: v0.1.1
          token: ${{ secrets.PAT_TOKEN }}
          path: ontology-quality-assessment

      # Updated path
      - name: Install dependencies
        run: |
          cd $GITHUB_WORKSPACE
          ln -s ontolint/pyproject.toml
          poetry install
       
      # Updated path
      - name: Check all ontologies
        run: | 
          poetry run ${GITHUB_WORKSPACE}/ontolint/scripts/ontology_qa.py path/to/your/ontology.ttl -e --ctrf-dir ctrf
        if: always()
        
      # Updated path
      - name: Generate CTRF report
        run: poetry run ${GITHUB_WORKSPACE}/ontolint/scripts/generate_custom_report.py --ctrf-dir ctrf --template-path ${GITHUB_WORKSPACE}/ontolint/templates/ctrf-report.hbs --output-path out/ctrf_report.md
        if: always()
```
