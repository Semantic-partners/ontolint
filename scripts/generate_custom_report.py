#!/usr/bin/env python3
"""Deprecated: run `ontolint-report` instead. Kept so existing invocations keep working."""
import sys

from _shim import run

if __name__ == "__main__":
    sys.exit(run("ontolint.report.ctrf_summary", "ontolint-report"))
