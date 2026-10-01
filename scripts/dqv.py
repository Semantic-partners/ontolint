"""
DQV (W3C Data Quality Vocabulary) report for ontolint.

Turns QAResults from ontology_qa.run_qa() into a DQV Turtle graph: one dqv:Metric per check,
one dqv:QualityMeasurement per (dataset, failed check) whose violations are SHACL
sh:ValidationResults, a per-dataset roll-up, and a dqv:QualityMetadata assessment. No blank
nodes are emitted: instance IRIs are minted under a base URI. The olq: vocabulary used here is
defined in ontology/olq.ttl.

This module has no dependency on ontology_qa; the checks there build the Violation records.
"""
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import rdflib


@dataclass
class Violation:
    """A single offending resource raised by a QA check (used for the DQV report)."""
    resource: object = None           # the offending resource: URIRef/BNode, or an IRI string
    comment: str | None = None        # optional human-readable message
    related: list = field(default_factory=list)  # other resources involved, e.g. a same-label clash
    value: object = None              # optional literal, e.g. the shared label


@dataclass
class ConfigSetting:
    """
    One setting of the configuration a QA run actually used, with where it came from.

    key:    the .rdf-lint.yml path it corresponds to, e.g. 'checks', 'imports.local'.
    value:  the IRI or value; for 'checks', the CHECKLIST key of the check.
    origin: 'config' (the .rdf-lint.yml file), 'default' (an ontolint default),
            'bundled' (a vocabulary bundled with ontolint) or 'rule' (added by an ontolint rule).
    """
    key: str
    value: object
    origin: str
    reason: str | None = None
    enabled: bool | None = None       # for 'checks'
    local_file: str | None = None     # for 'imports.local'
    derived_from: str | None = None   # e.g. the catalog dataset of a bundled vocabulary
    label: str | None = None          # for 'checks', the check's display name


@dataclass
class Dataset:
    """A dataset QA was computed on: an owl:Ontology IRI, or a file IRI as fallback."""
    iri: str
    label: str | None = None


# ── DQV (Data Quality Vocabulary) report ─────────────────────────────────────

DQV = rdflib.Namespace("http://www.w3.org/ns/dqv#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
DCAT = rdflib.DCAT
OLQ = rdflib.Namespace("https://ontolint.org/ns#")
SH = rdflib.SH

# All instance IRIs (metrics, dimensions, assessment, measurements, violations) are
# minted under this base unless --base-uri is given. OLQ holds only vocabulary terms.
DEFAULT_BASE_URI = "urn:ontolint:"
DEFAULT_DQV_FILENAME = "ontolint-dqv.ttl"

# slug -> (label, definition)
DQV_DIMENSIONS = {
    'metadata':      ("Metadata",      "The ontology declares itself and describes its purpose."),
    'documentation': ("Documentation", "Terms carry human-readable labels and descriptions."),
    'uniqueness':    ("Uniqueness",    "Labels and identifiers unambiguously denote a single term."),
    'structure':     ("Structure",     "Terms are connected into a well-formed hierarchy with domains and ranges."),
    'conformance':   ("Conformance",   "Terms are declared, resolvable and minted in the ontology's own namespace."),
}

# CHECKLIST key -> (metric slug, definition, dimension slug, default severity as a sh:Severity)
DQV_METRICS = {
    'ontologyNotDeclared':        ('ontology-not-declared',            "A processed file has no owl:Ontology declaration.",                                   'metadata',      SH.Violation),
    'ontologyDescription':        ('ontology-missing-description',     "A declared owl:Ontology has no rdfs:comment, dcterms:abstract or dcterms:description.", 'metadata',      SH.Violation),
    'unresolvedImports':          ('unresolvable-imports',             "An owl:imports target could not be resolved or contains no triples.",                  'conformance',   SH.Violation),
    'undefinedTerms':             ('undefined-terms',                  "A term is used but defined neither locally nor in its vocabulary (bundled, local or fetched).",       'conformance',   SH.Violation),
    'missingClassLabel':          ('classes-missing-label',            "A class has no label annotation.",                                                     'documentation', SH.Violation),
    'missingPropertyLabel':       ('properties-missing-label',         "A property has no label annotation.",                                                  'documentation', SH.Violation),
    'missingNSLabel':             ('node-shapes-missing-label',        "A SHACL NodeShape has no label annotation.",                                           'documentation', SH.Violation),
    'missingPSLabel':             ('property-shapes-missing-label',    "A SHACL PropertyShape has no label annotation.",                                       'documentation', SH.Violation),
    'missingClassDescription':    ('classes-missing-description',      "A class has no description annotation.",                                               'documentation', SH.Warning),
    'missingPropertyDescription': ('properties-missing-description',   "A property has no description annotation.",                                            'documentation', SH.Warning),
    'missingNSDescription':       ('node-shapes-missing-description',  "A SHACL NodeShape has no description annotation.",                                     'documentation', SH.Warning),
    'missingPSDescription':       ('property-shapes-missing-description', "A SHACL PropertyShape has no description annotation.",                              'documentation', SH.Warning),
    'nonUniqueClassLabels':       ('classes-same-label',               "Two or more classes share a label in the same language.",                              'uniqueness',    SH.Violation),
    'nonUniquePropertyLabels':    ('properties-same-label',            "Two or more properties share a label in the same language.",                           'uniqueness',    SH.Violation),
    'nonUniqueNSLabels':          ('node-shapes-same-label',           "Two or more SHACL NodeShapes share a label in the same language.",                     'uniqueness',    SH.Violation),
    'nonUniquePSLabels':          ('property-shapes-same-label',       "Two or more SHACL PropertyShapes share a label in the same language.",                 'uniqueness',    SH.Violation),
    'isolatedClasses':            ('isolated-classes',                 "A class is declared but not connected to the rest of the ontology.",                   'structure',     SH.Warning),
    'missingDomain':              ('properties-missing-domain',        "A property has no rdfs:domain.",                                                       'structure',     SH.Warning),
    'missingRange':               ('properties-missing-range',         "A property has no rdfs:range.",                                                        'structure',     SH.Warning),
    'nonUniqueIdentifiers':       ('non-unique-identifiers',           "The same IRI is declared as more than one kind of class or property.",                'uniqueness',    SH.Violation),
    'subclassCycles':             ('subclass-cycles',                  "A class is involved in an rdfs:subClassOf cycle.",                                     'structure',     SH.Violation),
    'untypedClasses':             ('untyped-classes',                  "A term in the ontology namespace is used as a class but not declared as owl:Class or rdfs:Class.", 'conformance', SH.Violation),
    'untypedProperties':          ('untyped-properties',               "A term in the ontology namespace is used as a property but not declared as one.",      'conformance',   SH.Violation),
    'hijacking':                  ('namespace-hijacking',              "A resource is defined using an external vocabulary's namespace.",                      'conformance',   SH.Violation),
}

# Roll-up metric: one measurement per dataset, so clean datasets still appear.
DQV_ROLLUP_METRIC = ('ontolint-conformance', "Ontolint conformance",
                     "Number of ontolint checks that failed for the dataset; 0 means every executed check passed.",
                     'conformance')


def file_iri(path):
    """Absolute file: IRI for a local path."""
    return Path(path).resolve().as_uri()


def metric_iri(base, slug):
    """Stable metric IRI: <base>metric-<slug>, the same for a check across runs and datasets."""
    return rdflib.URIRef(f"{base}metric-{slug}")


def dimension_iri(base, slug):
    """Stable dimension IRI: <base>dimension-<slug>."""
    return rdflib.URIRef(f"{base}dimension-{slug}")


# An absolute IRI: a scheme, then no whitespace or characters IRIs don't allow.
_ABSOLUTE_IRI = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>"{}|\\^`\x00-\x1f\x7f]*$')


def check_base_uri(base_uri):
    """Reject relative or malformed bases: minted IRIs would resolve against the report's location."""
    if not _ABSOLUTE_IRI.match(base_uri):
        raise ValueError(f"--base-uri must be an absolute IRI (e.g. https://example.org/qa/), got {base_uri!r}")


def _normalise_base(base_uri):
    base = base_uri or DEFAULT_BASE_URI
    check_base_uri(base)
    return base if base.endswith(('/', '#', ':')) else base + '/'


def _mint(base, kind, *parts):
    """Deterministic, collision-resistant instance IRI: <base><kind>-<sha256 of parts>."""
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]
    return rdflib.URIRef(f"{base}{kind}-{digest}")


def _resource_node(base, value, bnode_keys):
    """
    The IRI to emit for a violation's resource. Blank nodes (e.g. anonymous SHACL property
    shapes) are skolemized to <base>bnode-<hash> of their canonical label in the checked
    graph: unique per blank node, and stable across parses even though blank-node ids are not.
    """
    if value is None:
        return None
    if isinstance(value, rdflib.BNode):
        return _mint(base, 'bnode', bnode_keys.get(value, str(value)))
    return rdflib.URIRef(str(value))


def _hash_key(value):
    """Hash-key form of a violation value: N3 for RDF terms, so "x"@en and "x"@fr differ."""
    if value is None:
        return ''
    return value.n3() if isinstance(value, rdflib.term.Node) else str(value)


def _add_metric(g, base, slug, label, definition, dimension, severity=None):
    m = metric_iri(base, slug)
    g.add((m, rdflib.RDF.type, DQV.Metric))
    g.add((m, rdflib.SKOS.prefLabel, rdflib.Literal(label)))
    g.add((m, rdflib.RDFS.label, rdflib.Literal(label)))
    g.add((m, rdflib.SKOS.definition, rdflib.Literal(definition)))
    g.add((m, DQV.inDimension, dimension_iri(base, dimension)))
    if severity:
        g.add((m, OLQ.severity, severity))
    d = dimension_iri(base, dimension)
    d_label, d_definition = DQV_DIMENSIONS[dimension]
    g.add((d, rdflib.RDF.type, DQV.Dimension))
    g.add((d, rdflib.RDFS.label, rdflib.Literal(d_label)))
    g.add((d, rdflib.SKOS.prefLabel, rdflib.Literal(d_label)))
    g.add((d, rdflib.SKOS.definition, rdflib.Literal(d_definition)))
    return m


def _report_timestamp():
    """Now, or SOURCE_DATE_EPOCH (reproducible-builds convention) if set, in UTC."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return datetime.now(timezone.utc)


# ConfigSetting.origin -> olq:SettingOrigin individual (defined in ontology/olq.ttl)
SETTING_ORIGINS = {
    'config':  OLQ.ConfigFile,
    'default': OLQ.OntolintDefault,
    'bundled': OLQ.BundledVocabulary,
    'rule':    OLQ.OntolintRule,
}


def _setting_value(base, setting):
    if setting.key == 'checks':
        return metric_iri(base, DQV_METRICS[setting.value][0])
    value = str(setting.value)
    return rdflib.URIRef(value) if _ABSOLUTE_IRI.match(value) else rdflib.Literal(value)


def _add_configuration(g, base, settings, config_file=None):
    """
    The configuration a run actually used, as an olq:Configuration of olq:Settings. Each
    setting records the .rdf-lint.yml key it corresponds to, its value, its origin (the
    config file, an ontolint default, a bundled vocabulary or an ontolint rule) and why.
    Identical configurations get the same IRI.
    """
    # Describe every check's metric, including disabled checks that never ran.
    for s in settings:
        if s.key == 'checks':
            slug, definition, dimension, severity = DQV_METRICS[s.value]
            _add_metric(g, base, slug, s.label or slug, definition, dimension, severity)
    signature = sorted(f"{s.key}|{_setting_value(base, s)}|{s.origin}|{s.enabled}|{s.local_file}" for s in settings)
    configuration = _mint(base, 'configuration', config_file or '', *signature)
    g.add((configuration, rdflib.RDF.type, OLQ.Configuration))
    g.add((configuration, rdflib.RDFS.label, rdflib.Literal("Effective ontolint configuration")))
    if config_file:
        g.add((configuration, OLQ.configurationFile, rdflib.Literal(config_file)))
    for s in settings:
        value = _setting_value(base, s)
        node = _mint(base, 'setting', configuration, s.key, value, s.origin, s.enabled, s.local_file or '')
        g.add((configuration, OLQ.setting, node))
        g.add((node, rdflib.RDF.type, OLQ.Setting))
        shown = s.label if s.key == 'checks' and s.label else value
        label = f"{s.key}: {shown}" + ("" if s.enabled is None else (" (enabled)" if s.enabled else " (disabled)"))
        g.add((node, rdflib.RDFS.label, rdflib.Literal(label)))
        g.add((node, OLQ.key, rdflib.Literal(s.key)))
        g.add((node, OLQ.value, value))
        g.add((node, OLQ.origin, SETTING_ORIGINS[s.origin]))
        if s.enabled is not None:
            g.add((node, OLQ.enabled, rdflib.Literal(s.enabled)))
        if s.local_file:
            g.add((node, OLQ.localFile, rdflib.Literal(s.local_file)))
        if s.derived_from:
            g.add((node, PROV.wasDerivedFrom, rdflib.URIRef(s.derived_from)))
        if s.reason:
            g.add((node, rdflib.RDFS.comment, rdflib.Literal(s.reason)))
    return configuration


def build_dqv_graph(results, base_uri=None, timestamp=None):
    """
    Build a DQV graph from one or more QAResults (one per per-file run, or one merged run).

    - One dqv:Metric per executed check (<base>metric-<slug>), grouped by dqv:Dimension
      (<base>dimension-<slug>); both are stable for a given base.
    - One dqv:QualityMeasurement per (dataset, failed check), linking via olq:violation to one
      sh:ValidationResult per offending resource (sh:focusNode, sh:value, sh:resultMessage,
      sh:resultSeverity, sh:sourceConstraintComponent, plus olq:relatedResource).
    - One roll-up measurement per dataset (<base>metric-ontolint-conformance), so clean datasets appear.
    - A result is computed on its single dataset (owl:Ontology IRI, or file IRI fallback); a
      merged result over several is computed on one aggregate dcat:Dataset that
      dcterms:hasPart each of them, rather than being asserted on every ontology.
    - A dqv:QualityMetadata assessment node linking every measurement.
    No blank nodes are used: measurement, violation and assessment IRIs are hashes minted
    under base_uri. The olq: namespace is used only for vocabulary terms.
    """
    base = _normalise_base(base_uri)
    timestamp = timestamp or _report_timestamp()
    stamp = timestamp.isoformat()

    g = rdflib.Graph()
    for prefix, ns in [('dqv', DQV), ('olq', OLQ), ('sh', SH), ('prov', PROV), ('dcat', DCAT),
                       ('dcterms', rdflib.DCTERMS), ('skos', rdflib.SKOS),
                       ('rdfs', rdflib.RDFS), ('xsd', rdflib.XSD)]:
        g.bind(prefix, ns)

    run_files = sorted(f for r in results for f in r.profiling.get('filesProcessed', []))
    assessment = _mint(base, 'assessment', stamp, *run_files)
    g.add((assessment, rdflib.RDF.type, DQV.QualityMetadata))
    g.add((assessment, PROV.generatedAtTime, rdflib.Literal(stamp, datatype=rdflib.XSD.dateTime)))
    for result in results:
        if result.settings:
            configuration = _add_configuration(g, base, result.settings, result.config_file)
            g.add((assessment, OLQ.configuration, configuration))

    slug, label, definition, dimension = DQV_ROLLUP_METRIC
    rollup = _add_metric(g, base, slug, label, definition, dimension)

    for index, result in enumerate(results):
        # Distinguishes runs over different files that declare the same ontology IRI.
        run_key = sorted(result.profiling.get('filesProcessed', []))
        datasets = []
        for ds in result.datasets:
            iri = rdflib.URIRef(ds.iri)
            datasets.append(iri)
            if ds.label:
                g.add((iri, rdflib.RDFS.label, rdflib.Literal(ds.label)))
        if not datasets:
            # No owl:Ontology and no input files (e.g. an in-memory graph).
            dataset = _mint(base, 'dataset', assessment, index, *run_key)
        elif len(datasets) == 1:
            dataset = datasets[0]
        else:
            # A merged run over several ontologies can't attribute a violation to the one it
            # came from, so its results are computed on an aggregate of them (use --per-file
            # for per-ontology attribution). The aggregate is stable for the same inputs.
            dataset = _mint(base, 'dataset', *sorted(datasets), *run_key)
            names = [ds.label or ds.iri for ds in result.datasets]
            g.add((dataset, rdflib.RDF.type, DCAT.Dataset))
            g.add((dataset, rdflib.RDFS.label, rdflib.Literal("Merged: " + ", ".join(names))))
            for part in datasets:
                g.add((dataset, rdflib.DCTERMS.hasPart, part))

        for check in result.checks:
            info = DQV_METRICS.get(check.key)
            if info is None:
                continue
            m_slug, m_definition, m_dimension, severity = info
            metric = _add_metric(g, base, m_slug, check.name, m_definition, m_dimension, severity)
            if check.passed:
                continue
            measurement = _mint(base, 'measurement', assessment, *run_key, dataset, m_slug)
            g.add((assessment, DQV.hasQualityMeasurement, measurement))
            g.add((measurement, rdflib.RDF.type, DQV.QualityMeasurement))
            g.add((measurement, DQV.isMeasurementOf, metric))
            g.add((measurement, DQV.computedOn, dataset))
            g.add((measurement, DQV.value, rdflib.Literal(check.count)))
            g.add((measurement, OLQ.conforms, rdflib.Literal(False)))
            g.add((measurement, OLQ.severity, severity))
            for v in check.violations:
                resource = _resource_node(base, v.resource, result.bnode_keys)
                related = sorted((_resource_node(base, r, result.bnode_keys) for r in v.related), key=str)
                node = _mint(base, 'violation', measurement, resource or '', _hash_key(v.value),
                             v.comment or '', *related)
                g.add((measurement, OLQ.violation, node))
                # Each violation is a SHACL validation result. sh:sourceShape is omitted
                # until checks are expressed as shapes; the metric identifies the check.
                g.add((node, rdflib.RDF.type, SH.ValidationResult))
                g.add((node, SH.resultSeverity, severity))
                g.add((node, SH.sourceConstraintComponent, SH.SPARQLConstraintComponent))
                if resource is not None:
                    g.add((node, SH.focusNode, resource))
                if v.comment:
                    g.add((node, SH.resultMessage, rdflib.Literal(v.comment)))
                if v.value is not None:
                    value = v.value if isinstance(v.value, rdflib.Literal) else rdflib.Literal(v.value)
                    g.add((node, SH.value, value))
                for r in related:
                    g.add((node, OLQ.relatedResource, r))

        failed = len(result.failures)
        measurement = _mint(base, 'measurement', assessment, *run_key, dataset, slug)
        g.add((assessment, DQV.hasQualityMeasurement, measurement))
        g.add((measurement, rdflib.RDF.type, DQV.QualityMeasurement))
        g.add((measurement, DQV.isMeasurementOf, rollup))
        g.add((measurement, DQV.computedOn, dataset))
        g.add((measurement, DQV.value, rdflib.Literal(failed)))
        g.add((measurement, OLQ.conforms, rdflib.Literal(failed == 0)))

    return g


def check_dqv_filename(filename):
    """Reject anything but a plain file name, so the report can't escape --dqv-dir (and
    can't inject lines where the path is echoed, e.g. into $GITHUB_OUTPUT)."""
    if (not filename or filename in ('.', '..') or os.path.isabs(filename)
            or os.path.basename(filename) != filename or '/' in filename or '\\' in filename
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in filename)):
        raise ValueError(f"--dqv-filename must be a file name without directories or control characters, got {filename!r}; use --dqv-dir for the location")


def write_dqv_report(results, file_path, filename=None, base_uri=None, timestamp=None):
    """Serialise the DQV graph for the given QAResults to Turtle. Returns (graph, log)."""
    filename = filename or DEFAULT_DQV_FILENAME
    check_dqv_filename(filename)
    g = build_dqv_graph(results, base_uri=base_uri, timestamp=timestamp)
    os.makedirs(file_path, exist_ok=True)
    output_file = os.path.join(file_path, filename)
    g.serialize(destination=output_file, format='turtle')
    return g, f"\nDQV report written to: {output_file}\n"

def violation_bnodes(checks):
    return {t for check in checks for v in check.violations
            for t in (v.resource, *v.related) if isinstance(t, rdflib.BNode)}


def canonical_bnode_labels(graph, bnodes):
    """
    Canonical labels for the given blank nodes, unique across the whole graph and identical
    for any isomorphic parse (rdflib's RGDA1 canonicalisation). Structurally identical blank
    nodes, e.g. two `sh:property [ a sh:PropertyShape ]`, still get distinct labels.
    """
    if not bnodes:
        return {}
    from rdflib.compare import _TripleCanonicalizer
    # canonical_triples() yields the graph's triples in iteration order with blank nodes
    # relabelled, so pairing it with the graph gives the original -> canonical mapping.
    labels = {}
    for original, canonical in zip(graph, _TripleCanonicalizer(graph).canonical_triples()):
        for term, label in zip(original, canonical):
            if isinstance(term, rdflib.BNode) and labels.setdefault(term, str(label)) != str(label):
                raise RuntimeError("inconsistent blank-node canonicalisation")
    return {b: labels[b] for b in bnodes if b in labels}


def datasets_for(graph, qa_metrics):
    """
    The datasets a QA run was computed on: each declared owl:Ontology IRI (labelled from its
    rdfs:label, dcterms:title or skos:prefLabel), or, if none is declared, each input file's
    file: IRI.
    """
    ontologies = sorted({str(o) for o in qa_metrics.get('ontologyURI', [])})
    if not ontologies:
        return [Dataset(file_iri(f), os.path.basename(f)) for f in qa_metrics.get('filesProcessed', [])]
    datasets = []
    for iri in ontologies:
        label = None
        for p in (rdflib.RDFS.label, rdflib.DCTERMS.title, rdflib.SKOS.prefLabel):
            labels = sorted(graph.objects(rdflib.URIRef(iri), p), key=lambda lit: (getattr(lit, 'language', None) not in (None, 'en'), str(lit)))
            if labels:
                label = str(labels[0])
                break
        datasets.append(Dataset(iri, label))
    return datasets
