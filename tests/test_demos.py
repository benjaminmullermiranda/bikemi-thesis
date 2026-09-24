"""Runs every src module's assert-based demo() self-check under pytest."""
import importlib

import pytest


@pytest.mark.parametrize("module", ["costs", "data_io", "features", "injection", "model", "validation"])
def test_demo(module):
    importlib.import_module(f"src.{module}").demo()
