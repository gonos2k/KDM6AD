"""Shared pytest configuration for the harness suite."""

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_kernel_geometry: the test is ABOUT reading the private kernel "
        "source, so the public-checkout seam must not stand in for it")
