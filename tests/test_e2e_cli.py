import json
import os
from unittest.mock import patch
import pytest
import rdflib

from scripts.ontology_qa import main, parse_lint_config
from scripts import dqv

TESTS_DIR = os.path.join(os.path.dirname(__file__))


def run_main(*args):
    with patch('sys.argv', ['ontology_qa.py', *args]):
        main()


def test_example_pass_produces_no_failures(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path))
    reports = list(tmp_path.glob('*.json'))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert data['results']['summary']['failed'] == 0


def test_example_failure_produces_failures(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path))
    reports = list(tmp_path.glob('*.json'))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text())
    assert data['results']['summary']['failed'] > 0


def test_exit_status_raised_on_violations(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    with pytest.raises(SystemExit) as exc:
        run_main(ttl, '-e', '--ctrf-dir', str(tmp_path))
    assert exc.value.code == 1


def test_exit_status_zero_on_clean_ontology(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    run_main(ttl, '-e', '--ctrf-dir', str(tmp_path))  # must not raise


def test_profile_only_skips_qa_checks(tmp_path, capsys):
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(ttl, '-p', '--ctrf-dir', str(tmp_path))
    # profile-only exits before writing CTRF
    assert not list(tmp_path.glob('*.json'))
    out = capsys.readouterr().out
    assert "Profile-only mode" in out


def test_ctrf_filename_option(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path), '--ctrf-filename', 'my-report.json')
    assert (tmp_path / 'my-report.json').exists()


def test_ctrf_report_structure(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path))
    data = json.loads(list(tmp_path.glob('*.json'))[0].read_text())
    assert 'results' in data
    assert 'summary' in data['results']
    assert 'tests' in data['results']
    assert all('name' in t and 'status' in t for t in data['results']['tests'])


def test_nonexistent_file_prints_error(capsys):
    with patch('sys.argv', ['ontology_qa.py', 'nonexistent.ttl']):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "ERROR" in out or "Failed" in out

def test_inference_example_via_run_main(tmp_path, capsys):
    # :Fluffy a :Cat + :Cat subClassOf :Animal → inference adds :Fluffy a :Animal
    ttl = tmp_path / "inference_test.ttl"
    ttl.write_text("""@prefix : <http://example.org#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Animal a rdfs:Class.
    :Cat a rdfs:Class ; rdfs:subClassOf :Animal .
    :Fluffy a rdfs:Class, :Cat .
    """)
    run_main(str(ttl), '-i')
    out = capsys.readouterr().out
    assert "Added 1 new triples" in out
    assert "Final graph size after inference: 6 triples." in out
    assert "| inference_test.ttl | 6 | 3 | 0 |" in out
    
def test_no_inference(tmp_path, capsys):
    ttl = tmp_path / "inference_test.ttl"
    ttl.write_text("""@prefix : <http://example.org#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Animal a rdfs:Class.
    :Cat a rdfs:Class ; rdfs:subClassOf :Animal .
    :Fluffy a :Cat .
    """)
    run_main(str(ttl))
    out = capsys.readouterr().out
    assert "| inference_test.ttl | 4 | 2 | 0 |" in out


# ── --per-file ────────────────────────────────────────────────────────────────

def test_per_file_produces_one_ctrf_per_file(tmp_path):
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    fail_ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(pass_ttl, fail_ttl, '--per-file', '--ctrf-dir', str(tmp_path))
    reports = {r.name for r in tmp_path.glob('*.json')}
    assert 'example_pass-qa-report.json' in reports
    assert 'example_failure-qa-report.json' in reports
    assert len(reports) == 2


def test_per_file_ctrf_contents_reflect_individual_file(tmp_path):
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    fail_ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(pass_ttl, fail_ttl, '--per-file', '--ctrf-dir', str(tmp_path))
    pass_data = json.loads((tmp_path / 'example_pass-qa-report.json').read_text())
    fail_data = json.loads((tmp_path / 'example_failure-qa-report.json').read_text())
    assert pass_data['results']['summary']['failed'] == 0
    assert fail_data['results']['summary']['failed'] > 0


def test_per_file_exit_status_raised_when_any_file_fails(tmp_path):
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    fail_ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    with pytest.raises(SystemExit) as exc:
        run_main(pass_ttl, fail_ttl, '--per-file', '-e', '--ctrf-dir', str(tmp_path))
    assert exc.value.code == 1


def test_per_file_exit_status_zero_when_all_pass(tmp_path):
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    run_main(pass_ttl, '--per-file', '-e', '--ctrf-dir', str(tmp_path))  # must not raise


def test_per_file_no_files_found_exit_status(tmp_path, capsys):
    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        run_main(str(empty), '--per-file', '-e', '--ctrf-dir', str(tmp_path / 'ctrf'))
    assert exc.value.code == 1
    assert 'No RDF data in input files or directories.' in capsys.readouterr().out


def test_per_file_no_files_found_without_exit_status_returns(tmp_path, capsys):
    empty = tmp_path / 'empty'
    empty.mkdir()
    run_main(str(empty), '--per-file', '--ctrf-dir', str(tmp_path / 'ctrf'))  # must not raise
    assert 'No RDF data in input files or directories.' in capsys.readouterr().out


def test_per_file_output_contains_header_per_file(tmp_path, capsys):
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    fail_ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(pass_ttl, fail_ttl, '--per-file', '--ctrf-dir', str(tmp_path))
    out = capsys.readouterr().out
    assert out.count('# Ontology Quality Assurance') == 2


# ── exclude.types config ─────────────────────────────────────────────────────

def test_exclude_types_config_applied_via_main(tmp_path, capsys):
    ttl = tmp_path / "onto.ttl"
    ttl.write_text("""@prefix : <http://example.org#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    : a owl:Ontology .
    :Dog a owl:Class .
    :hasFur a owl:ObjectProperty ; rdfs:range :standIn1 .
    :standIn1 a rdf:PropositionForm .
    """)
    cfg = tmp_path / "lint.yml"
    cfg.write_text("exclude:\n  types:\n    - rdf:PropositionForm\n")
    ctrf_dir = tmp_path / "ctrf"
    run_main(str(ttl), '-c', str(cfg), '--ctrf-dir', str(ctrf_dir))
    data = json.loads(next(ctrf_dir.glob('*.json')).read_text())
    untyped = [t for t in data['results']['tests'] if t['name'] == 'Untyped Classes'][0]
    assert untyped['status'] == 'passed'
    assert 'rdf-syntax-ns#PropositionForm' in capsys.readouterr().out


# ── DQV output ────────────────────────────────────────────────────────────────

def _dqv_graph(path):
    import rdflib
    return rdflib.Graph().parse(str(path), format='turtle')


def test_dqv_not_written_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_main(os.path.join(TESTS_DIR, 'example_pass.ttl'), '--ctrf-dir', str(tmp_path / 'ctrf'))
    assert not list(tmp_path.rglob('*.ttl'))


def test_dqv_dir_writes_default_filename(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path / 'ctrf'), '--dqv-dir', str(tmp_path / 'dqv'))
    out = tmp_path / 'dqv' / 'ontolint-dqv.ttl'
    assert out.exists()
    assert len(_dqv_graph(out)) > 0


def test_dqv_filename_and_base_uri(tmp_path):
    from scripts.dqv import DQV
    import rdflib
    ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(ttl, '--ctrf-dir', str(tmp_path / 'ctrf'), '--dqv-dir', str(tmp_path),
             '--dqv-filename', 'report.ttl', '--base-uri', 'https://kh.example/qa#')
    g = _dqv_graph(tmp_path / 'report.ttl')
    measurements = list(g.subjects(rdflib.RDF.type, DQV.QualityMeasurement))
    assert measurements
    assert all(str(m).startswith('https://kh.example/qa#measurement-') for m in measurements)


def test_dqv_per_file_writes_single_report_covering_all_files(tmp_path):
    from scripts.dqv import DQV, OLQ
    import rdflib
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    fail_ttl = os.path.join(TESTS_DIR, 'example_failure.ttl')
    run_main(pass_ttl, fail_ttl, '--per-file', '--ctrf-dir', str(tmp_path / 'ctrf'), '--dqv-dir', str(tmp_path))
    g = _dqv_graph(tmp_path / 'ontolint-dqv.ttl')
    rollups = list(g.subjects(DQV.isMeasurementOf, rdflib.URIRef('urn:ontolint:metric-ontolint-conformance')))
    assert len(rollups) == 2
    assert {g.value(m, OLQ.conforms).toPython() for m in rollups} == {True, False}
    # One configuration per run, not one for the report: each file resolved against the
    # other, so what each run was given genuinely differs and the report names it (#108).
    configurations = set(g.subjects(rdflib.RDF.type, OLQ.Configuration))
    assert len(configurations) == 2
    resolved = {str(g.value(setting, OLQ.value))
                for configuration in configurations
                for setting in g.objects(configuration, OLQ.setting)
                if g.value(setting, OLQ.origin) == OLQ.RunInput}
    assert resolved, "a per-file run should name the inputs it resolved against"
    [assessment] = g.subjects(rdflib.RDF.type, DQV.QualityMetadata)
    assert set(g.objects(assessment, OLQ.configuration)) == configurations


def test_dqv_filename_with_directory_is_rejected(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    with pytest.raises(SystemExit) as exc:
        run_main(ttl, '--ctrf-dir', str(tmp_path / 'ctrf'), '--dqv-dir', str(tmp_path / 'dqv'),
                 '--dqv-filename', '../escape.ttl')
    assert exc.value.code == 2  # argparse usage error
    assert not (tmp_path / 'escape.ttl').exists()


def test_relative_base_uri_is_rejected(tmp_path):
    ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    with pytest.raises(SystemExit) as exc:
        run_main(ttl, '--ctrf-dir', str(tmp_path / 'ctrf'), '--dqv-dir', str(tmp_path), '--base-uri', 'qa')
    assert exc.value.code == 2  # argparse usage error
    assert not list(tmp_path.glob('*.ttl'))


# ── undefined-terms.skip-object-of config ─────────────────────────────────────

def _undefined_terms_status(ctrf_dir):
    data = json.loads(next(ctrf_dir.glob('*.json')).read_text())
    return [t for t in data['results']['tests'] if t['name'] == 'Undefined terms'][0]['status']


def test_skip_object_of_config_applied_via_main(tmp_path):
    ttl = tmp_path / "onto.ttl"
    ttl.write_text("""@prefix : <http://example.org#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    : a owl:Ontology .
    :Dog a owl:Class ; rdfs:seeAlso <https://example.invalid/docs/dog.html> .
    """)
    run_main(str(ttl), '--ctrf-dir', str(tmp_path / 'default'))
    assert _undefined_terms_status(tmp_path / 'default') == 'passed'

    # An empty list overrides the defaults, so the seeAlso target is checked (and fails).
    cfg = tmp_path / "lint.yml"
    cfg.write_text("undefined-terms:\n  skip-object-of: []\n")
    run_main(str(ttl), '-c', str(cfg), '--ctrf-dir', str(tmp_path / 'override'))
    assert _undefined_terms_status(tmp_path / 'override') == 'failed'



# ── parse failures ────────────────────────────────────────────────────────────

def test_parse_failure_exits_nonzero_without_exit_status_flag(tmp_path):
    bad = tmp_path / 'bad.ttl'
    bad.write_text('not valid turtle @@@ !!!')
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    ctrf_dir = tmp_path / 'ctrf'
    with pytest.raises(SystemExit) as exc:
        run_main(pass_ttl, str(bad), '--ctrf-dir', str(ctrf_dir))
    assert exc.value.code == 1
    # QA is not run against a partially loaded graph
    assert not list(ctrf_dir.glob('*.json'))


def test_parse_failure_reported_in_output(tmp_path, capsys):
    bad = tmp_path / 'bad.ttl'
    bad.write_text('not valid turtle @@@ !!!')
    with pytest.raises(SystemExit):
        run_main(str(bad), '--ctrf-dir', str(tmp_path))
    captured = capsys.readouterr()
    assert 'could not be parsed' in captured.out
    assert str(bad) in captured.err


def test_per_file_parse_failure_exits_nonzero_but_reports_other_files(tmp_path):
    bad = tmp_path / 'bad.ttl'
    bad.write_text('not valid turtle @@@ !!!')
    pass_ttl = os.path.join(TESTS_DIR, 'example_pass.ttl')
    ctrf_dir = tmp_path / 'ctrf'
    with pytest.raises(SystemExit) as exc:
        run_main(pass_ttl, str(bad), '--per-file', '--ctrf-dir', str(ctrf_dir))
    assert exc.value.code == 1
    assert [p.name for p in ctrf_dir.glob('*.json')] == ['example_pass-qa-report.json']


# ── one file, one ontology (issue #95) ────────────────────────────────────────

DUPLICATE_METRIC = rdflib.URIRef(f"{dqv.DEFAULT_BASE_URI}metric-duplicate-ontology-iri")

SAME_ONTOLOGY = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://example.org/thing#> a owl:Ontology ; rdfs:comment "Declared in both files" .
<https://example.org/thing#%s> a owl:Class ; rdfs:label "%s" ; rdfs:comment "A class" .
"""


def _duplicate_sources(report_path):
    """The inputs the report blames for a duplicated ontology IRI."""
    g = rdflib.Graph().parse(report_path, format='turtle')
    return {
        str(g.value(v, rdflib.SH.focusNode)):
            sorted(str(r) for r in g.objects(v, dqv.OLQ.relatedResource))
        for m in g.subjects(dqv.DQV.isMeasurementOf, DUPLICATE_METRIC)
        for v in g.objects(m, dqv.OLQ.violation)
    }


@pytest.fixture
def two_files_one_ontology(tmp_path):
    """Two input files declaring the same owl:Ontology IRI."""
    for name in ('alpha', 'beta'):
        (tmp_path / f"{name}.ttl").write_text(SAME_ONTOLOGY % (name, name))
    return tmp_path, [dqv.file_iri(tmp_path / f"{name}.ttl") for name in ('alpha', 'beta')]


@pytest.mark.parametrize('mode', [[], ['--per-file']])
def test_duplicate_ontology_iri_is_reported_naming_both_files(two_files_one_ontology, tmp_path, mode):
    # Merging the inputs first would hide this: two identical declarations are one triple,
    # so it is recorded while the files are still separate (load_rdf's ontology_sources).
    inputs, file_iris = two_files_one_ontology
    out = tmp_path / 'out'

    run_main(str(inputs), *mode, '--ctrf-dir', str(out / 'ctrf'), '--dqv-dir', str(out))

    assert _duplicate_sources(out / dqv.DEFAULT_DQV_FILENAME) == {
        "https://example.org/thing#": sorted(file_iris),
    }


def test_a_duplicate_does_not_stop_the_run(two_files_one_ontology, tmp_path):
    inputs, _ = two_files_one_ontology
    out = tmp_path / 'out'

    run_main(str(inputs), '--per-file', '--ctrf-dir', str(out / 'ctrf'), '--dqv-dir', str(out))

    # Both files were checked and reported, rather than the run aborting on the clash.
    assert len(list((out / 'ctrf').glob('*.json'))) == 2


def test_distinct_ontologies_raise_no_duplicate_finding(tmp_path):
    for name in ('one', 'two'):
        (tmp_path / f"{name}.ttl").write_text(
            SAME_ONTOLOGY.replace('thing', name) % ('Thing', 'Thing'))
    out = tmp_path / 'out'

    run_main(str(tmp_path), '--per-file', '--ctrf-dir', str(out / 'ctrf'), '--dqv-dir', str(out))

    assert _duplicate_sources(out / dqv.DEFAULT_DQV_FILENAME) == {}


# --- The flag combinations the two main() paths disagree about ------------------------
#
# Each of these is a behavioural difference between the single-run and per-file paths, so
# collapsing them (#96) has to decide what the combination means. Pinned first, so the
# collapse is a deliberate change rather than an accident.

DATA_DIR = os.path.join(TESTS_DIR, 'data')
REPORTERS = os.path.join(DATA_DIR, 'reporters.ttl')
FRAGMENT = os.path.join(DATA_DIR, 'fragment.ttl')


def test_output_option_writes_the_report_to_a_file(tmp_path, capsys):
    out = tmp_path / 'report.md'
    run_main(REPORTERS, '-o', str(out), '--ctrf-dir', str(tmp_path / 'ctrf'))

    report = out.read_text()
    assert '## Quality Assurance Checks' in report
    # Written *instead of* printed, not as well as.
    assert capsys.readouterr().out == ''


def test_output_option_creates_missing_directories(tmp_path):
    out = tmp_path / 'nested' / 'deeper' / 'report.md'
    run_main(REPORTERS, '-o', str(out), '--ctrf-dir', str(tmp_path / 'ctrf'))

    assert out.exists()


def test_output_option_holds_every_report_with_per_file(tmp_path, capsys):
    out = tmp_path / 'report.md'
    run_main(REPORTERS, FRAGMENT, '--per-file', '-o', str(out),
             '--ctrf-dir', str(tmp_path / 'ctrf'))

    # Per-file already concatenated its reports onto one stream; -o writes that stream to
    # a file rather than dropping it, so the flag means the same thing in both modes.
    report = out.read_text()
    assert report.count('# Ontology Quality Assurance') == 2
    assert 'reporters.ttl' in report and 'fragment.ttl' in report
    assert capsys.readouterr().out == ''


def test_per_file_names_each_ctrf_report_after_its_input(tmp_path):
    ctrf = tmp_path / 'ctrf'
    run_main(REPORTERS, FRAGMENT, '--per-file', '--ctrf-dir', str(ctrf))

    assert sorted(p.name for p in ctrf.glob('*.json')) == [
        'fragment-qa-report.json', 'reporters-qa-report.json']


def test_ctrf_filename_is_refused_with_per_file(tmp_path, capsys):
    # One name cannot hold a report per input. It used to be accepted and ignored, which
    # silently gave the caller something other than what they asked for.
    with pytest.raises(SystemExit) as exit_info:
        run_main(REPORTERS, FRAGMENT, '--per-file', '--ctrf-filename', 'custom.json',
                 '--ctrf-dir', str(tmp_path / 'ctrf'))

    assert exit_info.value.code == 2
    assert '--ctrf-filename' in capsys.readouterr().err


def test_empty_directory_in_a_single_run_reports_no_rdf_data(tmp_path, capsys):
    empty = tmp_path / 'empty'
    empty.mkdir()
    run_main(str(empty), '--ctrf-dir', str(tmp_path / 'ctrf'))

    assert 'ERROR - No RDF data in input files or directories.' in capsys.readouterr().out
    assert not (tmp_path / 'ctrf').exists() or not list((tmp_path / 'ctrf').glob('*.json'))


def test_empty_directory_in_a_single_run_raises_the_exit_status(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()

    with pytest.raises(SystemExit) as exit_info:
        run_main(str(empty), '-e', '--ctrf-dir', str(tmp_path / 'ctrf'))

    assert exit_info.value.code == 1


def test_profile_only_with_per_file_writes_nothing_and_runs_no_checks(tmp_path, capsys):
    ctrf = tmp_path / 'ctrf'
    run_main(REPORTERS, FRAGMENT, '--per-file', '-p', '--ctrf-dir', str(ctrf))

    out = capsys.readouterr().out
    # Profiling for each input, and no checks: the one combination that produces no CTRF
    # and no QA report at all.
    assert out.count('## Profiling Details') == 2
    assert '## Quality Assurance Checks' not in out
    assert not ctrf.exists() or not list(ctrf.glob('*.json'))


# --- Verbose output -------------------------------------------------------------------

VERBOSE_ONLY = [
    '**Ontology + Description:**',
    'PASS - Found 1 ontology with `owl:Ontology` declaration:',
    'List of deprecated classes:',
    '| NodeShape | Class count |',
    '| PropertyShape | Local Property |',
    '| Ontology | Import URL | Resolves? |',
]


def test_verbose_adds_the_detail_tables(tmp_path, capsys):
    run_main(REPORTERS, '--ctrf-dir', str(tmp_path / 'ctrf'))
    plain = capsys.readouterr().out
    run_main(REPORTERS, '-v', '--ctrf-dir', str(tmp_path / 'ctrf'))
    verbose = capsys.readouterr().out

    for marker in VERBOSE_ONLY:
        assert marker in verbose, f"-v should add {marker!r}"
        assert marker not in plain, f"{marker!r} is not verbose-only after all"


def test_verbose_renders_the_same_text_every_time(tmp_path, capsys):
    run_main(REPORTERS, '-v', '--ctrf-dir', str(tmp_path / 'ctrf'))
    first = capsys.readouterr().out
    run_main(REPORTERS, '-v', '--ctrf-dir', str(tmp_path / 'ctrf'))

    # -v was the last mode to become reproducible; nothing it adds may reintroduce a
    # blank node identifier or an unsorted list.
    assert capsys.readouterr().out == first


# ── resolving against the other inputs of the same run (#108) ─────────────────

def _family(tmp_path):
    """Two ontologies developed together: one refers to the other, neither is published."""
    (tmp_path / 'core.ttl').write_text("""
@prefix core: <https://example.org/core#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
core: a owl:Ontology ; rdfs:label "Core" ; rdfs:comment "Shared concepts." .
core:Thing a owl:Class ; rdfs:label "Thing" ; rdfs:comment "Anything at all." .
""")
    (tmp_path / 'domain.ttl').write_text("""
@prefix dom:  <https://example.org/domain#> .
@prefix core: <https://example.org/core#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
dom: a owl:Ontology ; rdfs:label "Domain" ; rdfs:comment "Builds on core." .
dom:Widget a owl:Class ; rdfs:label "Widget" ; rdfs:comment "A widget." ;
    rdfs:subClassOf core:Thing .
""")
    return str(tmp_path / 'core.ttl'), str(tmp_path / 'domain.ttl')


def test_a_per_file_run_resolves_against_the_other_inputs(tmp_path, capsys):
    """
    A family linted per file needs no imports.local entries for its own members.

    Without this each file is linted alone, so a reference to a sibling is a term in a
    namespace that cannot be fetched — the report said `(fetch failure)` for an ontology
    sitting in the same directory.
    """
    core, domain = _family(tmp_path)
    run_main(core, domain, '--per-file', '--ctrf-dir', str(tmp_path / 'ctrf'))
    report = capsys.readouterr().out
    assert 'fetch failure' not in report
    assert "another input: `" in report, "the report should say which input resolved it"


def test_an_input_speaks_only_for_the_ontology_it_declares(tmp_path, capsys):
    """
    A sibling is registered for what it declares, not for every namespace it touches.

    Registering it for all of them lets one input shadow a real vocabulary by minting a
    term in its namespace — which tests/example_failure.ttl does to SKOS, and which made
    skos:prefLabel undefined in the file linted beside it.
    """
    core, domain = _family(tmp_path)
    (tmp_path / 'hijacker.ttl').write_text("""
@prefix hij:  <https://example.org/hijacker#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
hij: a owl:Ontology ; rdfs:label "Hijacker" ; rdfs:comment "Mints in someone else's namespace." .
skos:inventedHere a owl:Class ; rdfs:label "Invented" ; rdfs:comment "Not a SKOS term." .
""")
    (tmp_path / 'uses_skos.ttl').write_text("""
@prefix u:    <https://example.org/uses#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
u: a owl:Ontology ; rdfs:label "Uses" ; rdfs:comment "Uses a real SKOS term." .
u:Term a owl:Class ; rdfs:label "Term" ; rdfs:comment "A term." ; skos:prefLabel "term" .
""")
    run_main(str(tmp_path / 'hijacker.ttl'), str(tmp_path / 'uses_skos.ttl'),
             '--per-file', '--ctrf-dir', str(tmp_path / 'ctrf'))
    report = capsys.readouterr().out
    assert 'skos/core#prefLabel' not in report, "the bundled SKOS must still answer for skos:"


def test_a_merged_run_needs_no_sibling_context(tmp_path, capsys):
    """Merged, every input is already in the graph, so nothing is resolved as a sibling."""
    core, domain = _family(tmp_path)
    run_main(core, domain, '--ctrf-dir', str(tmp_path / 'ctrf'))
    report = capsys.readouterr().out
    assert 'fetch failure' not in report
    assert "another input: `" not in report


def test_imports_siblings_false_checks_each_input_alone(tmp_path, capsys):
    """
    A project can turn sibling resolution off, and is told in the report that it did.

    Resolving against the run is on by default, but a directory of unrelated ontologies
    may want each judged strictly on its own — with a reference to a neighbour reported
    as the unresolvable reference it would be anywhere else.
    """
    core, domain = _family(tmp_path)
    (tmp_path / '.rdf-lint.yml').write_text("imports:\n  siblings: false\n")
    run_main(core, domain, '--per-file', '--config', str(tmp_path / '.rdf-lint.yml'),
             '--ctrf-dir', str(tmp_path / 'ctrf'))
    assert 'fetch failure' in capsys.readouterr().out


def test_imports_siblings_must_be_a_boolean(tmp_path):
    (tmp_path / '.rdf-lint.yml').write_text("imports:\n  siblings: sometimes\n")
    with pytest.raises(ValueError, match="imports.siblings must be true or false"):
        parse_lint_config(str(tmp_path / '.rdf-lint.yml'))
