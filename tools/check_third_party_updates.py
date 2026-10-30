#!/usr/bin/env python3
"""Shim until 2026-12-01: the workflow still calls the old name (harbor#967); remove with the workflow patch."""

import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().with_name("check-third-party-updates.py")
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
