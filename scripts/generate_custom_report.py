#!/usr/bin/env python3
"""Deprecated: run `ontolint-report` instead. Kept so existing invocations keep working."""
import sys

from ontolint.report.ctrf_summary import main

if __name__ == "__main__":
    sys.exit(main())
