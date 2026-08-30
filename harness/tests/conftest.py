"""Shared pytest configuration for the harness suite."""
import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--local", action="store_true", default=False,
        help="run the tests marked `local`: the ones that walk the gitignored "
             "host tree, its bundles, or spawn gfortran. Off by default; on "
             "under CI (which skips what it cannot reach anyway).")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_kernel_geometry: the test is ABOUT reading the private kernel "
        "source, so the public-checkout seam must not stand in for it")
    config.addinivalue_line(
        "markers",
        "local: needs the gitignored host tree, its bundles, or gfortran. "
        "Deselected unless --local or CI=true.")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--local") or os.environ.get("CI"):
        return
    keep, drop = [], []
    for it in items:
        (drop if it.get_closest_marker("local") else keep).append(it)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
