#!/usr/bin/env python3
"""Compatibility CLI for the canonical package audit implementation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qtranslate.audit.legacy import *
if __name__=='__main__':main()
