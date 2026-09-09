import runsentry


def test_package_imports_and_exposes_version() -> None:
    assert runsentry.__version__ == "0.1.0a1"
