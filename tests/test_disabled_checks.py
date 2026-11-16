"""
A check turned off by the configuration is listed in every report, in its place, as disabled
and with why (#125). Disabled is not skipped: skipped ran and could not be computed, disabled
was never run.
"""
import json
import re
import subprocess
import sys

import pytest
import rdflib

from ontolint import dqv
from ontolint.config import lint_selection
from ontolint.dqv import DQV, OLQ
from ontolint.registry import CHECKLIST, deepcopy_list
from ontolint.report.ctrf import build_ctrf_report, write_ctrf_report
from ontolint.report.markdown import render_markdown
from ontolint.runner import run_qa

CONFIG_FILE = ".rdf-lint.yml"
# No properties and no shapes, so their checks are skipped (nothing to examine) in the same
# run that disables hijacking: the two outcomes have to stay distinguishable side by side.
ONTOLOGY = """
: a owl:Ontology ; rdfs:comment "Disabled checks" .
:Thing a owl:Class ; rdfs:label "Thing" ; rdfs:comment "A thing." .
"""


def _run(make_graph, lint_config):
    rule_reasons = {}
    checklist, _ = lint_selection(lint_config, deepcopy_list(CHECKLIST), rule_reasons)
    return run_qa(make_graph(ONTOLOGY), checklist=checklist, lint_config=lint_config,
                  rule_reasons=rule_reasons, config_file=CONFIG_FILE,
                  uri_parser=lambda iri: rdflib.Graph())


@pytest.fixture
def result(make_graph):
    return _run(make_graph, {"disable": ["check_hijacking"]})


def _position(name):
    return next(i for i, (_, _, display, _) in enumerate(CHECKLIST, start=1) if display == name)


# ── the run ───────────────────────────────────────────────────────────────────

def test_a_disabled_check_is_listed_in_its_place_with_why(result):
    assert [c.name for c in result.checks] == [display for _, _, display, _ in CHECKLIST]
    [hijacking] = [c for c in result.checks if c.name == "Namespace hijacking"]
    assert hijacking.status == 'disabled'
    assert hijacking.reason == f"listed under disable: in {CONFIG_FILE}"


def test_a_check_left_out_of_enable_says_so(make_graph):
    result = _run(make_graph, {"enable": ["check_class_missing_label"]})
    disabled = [c for c in result.checks if c.status == 'disabled']
    assert disabled and {c.reason for c in disabled} == {f"not listed under enable: in {CONFIG_FILE}"}


def test_disabled_and_skipped_stay_distinct_and_neither_fails_the_run(result):
    statuses = {c.name: c.status for c in result.checks}
    assert statuses["Namespace hijacking"] == 'disabled'
    assert statuses["NodeShape without label"] == 'skipped'
    assert result.get("Namespace hijacking").passed
    assert result.passed == all(c.status != 'failed' for c in result.checks)


# ── Markdown ──────────────────────────────────────────────────────────────────

def test_markdown_shows_it_inline_as_disabled(result):
    rendered = render_markdown(result)
    position = _position("Namespace hijacking")
    assert (f"\nCheck {position}: Namespace hijacking.\n"
            f"DISABLED - listed under disable: in {CONFIG_FILE}.\n") in rendered
    assert "## Disabled" not in rendered      # inline among the checks, not a section


def test_markdown_table_says_disabled_not_na_or_skipped(result):
    rows = [line for line in render_markdown(result).splitlines() if line.startswith('|')]
    header = next(i for i, line in enumerate(rows) if 'Namespace hijacking' in line)
    cells = dict(zip((c.strip() for c in rows[header].split('|')),
                     (c.strip() for c in rows[header + 2].split('|'))))
    assert cells['Namespace hijacking'] == 'disabled'
    assert cells['NodeShapes without label'] == 'skipped'


# ── CTRF and its Markdown summary ─────────────────────────────────────────────

def test_ctrf_lists_it_as_other_with_raw_status_disabled(result):
    report = build_ctrf_report(result)['results']
    [entry] = [t for t in report['tests'] if t['name'] == "Namespace hijacking"]
    assert entry == {"name": "Namespace hijacking", "status": "other", "rawStatus": "disabled",
                     "message": f"disabled: listed under disable: in {CONFIG_FILE}"}
    summary = report['summary']
    assert summary['tests'] == len(CHECKLIST)
    assert summary['other'] == 1
    assert summary['skipped'] == sum(1 for t in report['tests'] if t['status'] == 'skipped') > 0
    assert sum(summary[k] for k in ('passed', 'failed', 'skipped', 'other')) == summary['tests']


def test_the_job_summary_counts_and_lists_it_as_disabled(result, tmp_path):
    ctrf_dir = tmp_path / "ctrf"
    write_ctrf_report(build_ctrf_report(result), str(ctrf_dir), "report.json")
    output = tmp_path / "summary.md"
    subprocess.run([sys.executable, "-m", "ontolint.report.ctrf_summary", "--ctrf-dir", str(ctrf_dir),
                    "--output-path", str(output)], check=True, capture_output=True)
    summary = output.read_text(encoding="utf-8")
    skipped = sum(1 for c in result.checks if c.status == 'skipped')
    assert "| File | Tests | Passed | Failed | Skipped | Disabled |" in summary
    assert re.search(rf"\| report \| {len(CHECKLIST)} \| \d+ \| \d+ \| {skipped} \| 1 \|", summary), summary
    assert f"| {skipped} skipped | 1 disabled" in summary
    assert (f"| Namespace hijacking | ⏸️ DISABLED | 0 | disabled: listed under disable: in "
            f"{CONFIG_FILE} |") in summary


# ── DQV ───────────────────────────────────────────────────────────────────────

def test_dqv_records_it_per_dataset_as_disabled_by_its_setting(result):
    g = dqv.build_dqv_graph([result])
    metric = rdflib.URIRef(dqv.metric_iri(dqv.DEFAULT_BASE_URI, 'namespace-hijacking'))
    [node] = list(g.subjects(OLQ.metric, metric))
    assert (node, rdflib.RDF.type, OLQ.Disabled) in g
    assert (None, OLQ.disabled, node) in g
    assert g.value(node, DQV.computedOn) is not None
    assert str(g.value(node, rdflib.RDFS.comment)) == f"Disabled: listed under disable: in {CONFIG_FILE}"
    setting = g.value(node, OLQ.disabledBy)
    assert (setting, rdflib.RDF.type, OLQ.Setting) in g
    assert g.value(setting, OLQ.enabled).toPython() is False
    assert g.value(setting, OLQ.value) == metric


def test_dqv_does_not_report_it_as_not_assessed_or_measured(result):
    g = dqv.build_dqv_graph([result])
    metric = rdflib.URIRef(dqv.metric_iri(dqv.DEFAULT_BASE_URI, 'namespace-hijacking'))
    assert not any((n, rdflib.RDF.type, OLQ.NotAssessed) in g for n in g.subjects(OLQ.metric, metric))
    assert not list(g.subjects(DQV.isMeasurementOf, metric))
    # The skipped shape checks are still olq:NotAssessed, so the two remain distinct.
    assert list(g.subjects(rdflib.RDF.type, OLQ.NotAssessed))


def test_a_cli_run_shows_it_in_every_report(tmp_path, monkeypatch):
    # The path the issue was reported on: a config file given with -c.
    from ontolint.cli import main
    from tests.conftest import REPORTERS_TTL
    config = tmp_path / "lint.yml"
    config.write_text("disable:\n  - undefined-terms\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["ontolint", str(REPORTERS_TTL), "-c", str(config),
                                      "--ctrf-dir", "ctrf", "--dqv-dir", "dqv", "-o", "report.md"])
    main()
    assert "DISABLED - listed under disable: in lint.yml." in (tmp_path / "report.md").read_text(encoding="utf-8")
    ctrf = json.loads(next((tmp_path / "ctrf").glob("*.json")).read_text(encoding="utf-8"))
    assert any(t.get("rawStatus") == "disabled" and t["name"] == "Undefined terms"
               for t in ctrf["results"]["tests"])
    g = rdflib.Graph().parse(next((tmp_path / "dqv").glob("*.ttl")))
    assert list(g.subjects(rdflib.RDF.type, OLQ.Disabled))
