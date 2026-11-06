#!/usr/bin/env python3
"""Deprecated: run `ontolint` instead. Kept so existing invocations keep working."""
import sys

from ontolint.cli import main

if __name__ == "__main__":
    sys.exit(main())
