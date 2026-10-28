"""
QAResult -> DQV, from the same result as tests/test_pipeline_lint_to_qaresult.py.

The DQV report is the structured form of a run: a measurement per failed check, each
violation a sh:ValidationResult naming the resource, and a conformance roll-up per dataset.
Unlike Markdown and CTRF it describes the whole run rather than one result, which is why
set-level findings can only live here.

tests/test_dqv.py covers the vocabulary and minting rules; this is about the projection.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import rdflib
from unittest.mock import patch
from rdflib.compare import graph_diff

from scripts import dqv
from scripts.dqv import build_dqv_graph, DQV_METRICS, DQV, DEFAULT_BASE_URI
from tests.conftest import CASES, stored_dqv_for, stored_qa_result_for
from tests.golden import stable_mint_id

EX = "https://example.org/reporters#"
ROLLUP = rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-ontolint-conformance")


def _metric(check_key):
    return rdflib.URIRef(f"{DEFAULT_BASE_URI}metric-{DQV_METRICS[check_key][0]}")


def _measured(graph):
    """{metric slug: value} for every check measurement, excluding the roll-up."""
    return {
        str(graph.value(m, DQV.isMeasurementOf)).rsplit('metric-', 1)[-1]:
            graph.value(m, DQV.value).toPython()
        for m in graph.subjects(rdflib.RDF.type, DQV.QualityMeasurement)
        if graph.value(m, DQV.isMeasurementOf) != ROLLUP
    }


# The instant the stored report was built at, passed in rather than read from the
# environment so the test says which clock it means.
AT = datetime(2026, 10, 15, 9, 30, 0, tzinfo=timezone.utc)

DATA = Path(__file__).parent / 'data'


@pytest.mark.parametrize('case', CASES)
def test_it_builds_the_stored_report(case):
    """
    The projection, whole. Everything below says which part of it must hold, and why.

    One report per case, as for the other reporters. A report covering several results is
    not the union of theirs — a measurement IRI hashes the assessment node it hangs from —
    so multi-result runs are pinned end-to-end in tests/dqv/, where `per-file/` and
    `merged/` cover both shapes against the CLI.
    """
    with patch.object(dqv, 'mint_id', stable_mint_id):
        graph = build_dqv_graph([stored_qa_result_for(case)], date_time_provider=lambda: AT)
    stored_path = DATA / f'{case}_dqv.ttl'
    if os.environ.get('UPDATE_GOLDEN'):
        stored_path.write_text(graph.serialize(format='turtle'), encoding='utf-8')
        pytest.skip(f"updated {stored_path.name}")

    in_report, in_stored = graph_diff(graph, stored_dqv_for(case))[1:]
    assert not list(in_report) and not list(in_stored), _diff_message(in_report, in_stored)


def _diff_message(in_report, in_stored):
    def lines(label, triples):
        shown = sorted(f"    {s} {p} {o}" for s, p, o in triples)[:10]
        return f"  {label} ({len(triples)}):\n" + "\n".join(shown) if len(triples) else ""
    return ("the built report and its stored copy under tests/data/ differ\n"
            + lines("only in the built report", in_report)
            + lines("only in the stored report", in_stored)
            + "\n  regenerate with: UPDATE_GOLDEN=1 poetry run pytest tests/test_pipeline_qaresult_to_dqv.py")


def test_the_graph_has_no_blank_nodes(stored_qa_result):
    # Every node is minted or skolemized, so a report can be merged with another without
    # its blank nodes colliding.
    graph = build_dqv_graph([stored_qa_result])

    assert not [t for triple in graph for t in triple if isinstance(t, rdflib.BNode)]
