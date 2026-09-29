#!/usr/bin/env python3
"""
CI check for an ontolint DQV report.

    assert_dqv.py REPORT.ttl --conforms      every dataset passed, no failing measurements
    assert_dqv.py REPORT.ttl --violations    at least one dataset failed, with violation nodes
    [--datasets N]                           expect exactly N datasets (roll-up measurements)

Prints a short summary (also appended to $GITHUB_STEP_SUMMARY when set).
"""
import argparse
import os
import sys

import rdflib

DQV = rdflib.Namespace("http://www.w3.org/ns/dqv#")
OLQ = rdflib.Namespace("https://ontolint.org/ns#")
SH = rdflib.SH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--conforms", action="store_true")
    mode.add_argument("--violations", action="store_true")
    parser.add_argument("--datasets", type=int)
    args = parser.parse_args()

    g = rdflib.Graph().parse(args.report, format="turtle")
    errors = []

    if any(isinstance(t, rdflib.BNode) for triple in g for t in triple):
        errors.append("report contains blank nodes")

    measurements = set(g.subjects(rdflib.RDF.type, DQV.QualityMeasurement))
    rollups = {m for m in measurements if str(g.value(m, DQV.isMeasurementOf)).endswith("metric-ontolint-conformance")}
    failing = {m for m in measurements - rollups if g.value(m, OLQ.conforms) == rdflib.Literal(False)}
    results = set(g.subjects(rdflib.RDF.type, SH.ValidationResult))

    if not rollups:
        errors.append("no roll-up (ontolint-conformance) measurements")
    if args.datasets is not None and len(rollups) != args.datasets:
        errors.append(f"expected {args.datasets} dataset(s), found {len(rollups)}")
    for m in failing:
        if not list(g.objects(m, OLQ.violation)):
            errors.append(f"failing measurement {m} has no olq:violation")

    conforming = {m for m in rollups if g.value(m, OLQ.conforms) == rdflib.Literal(True)}
    if args.conforms and (failing or conforming != rollups):
        errors.append(f"expected every dataset to conform; {len(failing)} failing measurement(s)")
    if args.violations and not (failing and results):
        errors.append("expected failing measurements with violations, found none")

    lines = [
        f"### DQV report `{os.path.basename(args.report)}`",
        "",
        f"- {len(g)} triples, {len(rollups)} dataset(s) ({len(conforming)} conforming)",
        f"- {len(failing)} failing measurement(s), {len(results)} violation(s)",
    ]
    for m in sorted(failing, key=lambda m: str(g.value(m, DQV.isMeasurementOf))):
        metric = g.value(m, DQV.isMeasurementOf)
        lines.append(f"  - {g.value(metric, rdflib.RDFS.label)}: {g.value(m, DQV.value)} "
                     f"on `{g.value(m, DQV.computedOn)}`")
    lines.append("")
    lines.append("❌ " + "; ".join(errors) if errors else "✅ DQV report as expected")
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
