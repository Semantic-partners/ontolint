"""
The CTRF report: one test per check, for CI to read.

A check that could not be computed is reported as skipped, with a message naming what it
needed, rather than as the pass its count of zero would otherwise suggest.
"""
from datetime import datetime
import json
import os

try:  # imported as part of the scripts package (e.g. by the tests)
    from scripts.model import not_assessed_message, QAResult
except ImportError:  # run as a script: scripts/ itself is on sys.path
    from model import not_assessed_message, QAResult


def build_ctrf_report(result: QAResult, date_time_provider=datetime.now):
    """
    A QAResult as a CTRF (Common Test Result Format) report: one test case per executed
    check, with the run's summary. Returns the report; writing it is write_ctrf_report's
    job, so the projection can be built and inspected without touching the filesystem.

    date_time_provider supplies the report's timestamp. It is injected so a caller can fix
    it — without that the projection is not a pure function of the QAResult, and two
    reports built over the same result differ. It is also the only way to fix it: a CTRF
    report written by the CLI carries the wall clock and is not reproducible.
    """
    counts = {'passed': 0, 'failed': 0, 'skipped': 0}
    by_key = {c.key: c for c in result.checks}
    test_cases = []

    for check in result.checks:
        test_case = {
            "name": check.name,
            "status": check.status
        }
        if check.status == 'failed':
            test_case["failure"] = {
                "violations": check.count,
                "elements": check.elements
            }
        elif check.status == 'skipped':
            # Not a pass: the check could not be computed, so the 0 means nothing.
            test_case["message"] = not_assessed_message(check, by_key)
        counts[check.status] += 1
        test_cases.append(test_case)
    
    # Build CTRF report
    ctrf_report = {
        "results": {
            "tool": {
                "name": "Ontology QA",
                "version": "2025-11-17"
            },
            "summary": {
                "tests": len(test_cases),
                "passed": counts['passed'],
                "failed": counts['failed'],
                "skipped": counts['skipped']
            },
            "tests": test_cases,
            "filesProcessed": result.profiling.get("filesProcessed", []),
            "timestamp": date_time_provider().strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    return ctrf_report


def write_ctrf_report(ctrf_report, file_path, filename):
    """Write a CTRF report (see build_ctrf_report) to a file. Returns the log line."""
    os.makedirs(file_path, exist_ok=True)
    # Fallback CTRF filename
    if not filename:
        filename = f'ontology-qa-report-{os.getpid()}.json'
    output_file = os.path.join(file_path, filename)
    with open(output_file, 'w') as f:
        json.dump(ctrf_report, f, indent=2)

    return f"\nCTRF report written to: {output_file}\n"
