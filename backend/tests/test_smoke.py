"""Phase 0 check: the package tree is importable and pytest is wired up."""


def test_sim_package_imports():
    import sim

    assert sim.__doc__
