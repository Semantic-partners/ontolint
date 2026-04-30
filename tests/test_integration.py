import json
import sys
import os
from unittest.mock import patch
import pytest

from scripts.ontology_qa import main, run_qa

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
        main()
    out = capsys.readouterr().out
    assert "ERROR" in out or "Failed" in out

# Disabled test, as the inference function is now called in main()
# def test_inference_log_reports_new_triples(make_graph):
#     # :Fluffy a :Cat + :Cat subClassOf :Animal → inference adds :Fluffy a :Animal
#     g = make_graph("""
#     :Animal a owl:Class .
#     :Cat a owl:Class ; rdfs:subClassOf :Animal .
#     :Fluffy a :Cat .
#     """)
#     result = run_qa(g)
#     assert "Added 1 new triples" in result.inference_log

def test_inference_example_via_run_main(tmp_path, capsys):
    # :Fluffy a :Cat + :Cat subClassOf :Animal → inference adds :Fluffy a :Animal
    ttl = tmp_path / "inference_test.ttl"
    ttl.write_text("""@prefix : <http://example.org#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    :Animal a rdfs:Class.
    :Cat a rdfs:Class ; rdfs:subClassOf :Animal .
    :Fluffy a :Cat .
    """)
    run_main(str(ttl), '-i')
    out = capsys.readouterr().out
    assert "Added 1 new triples" in out
