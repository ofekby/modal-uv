from example_pkg.main import greet


def test_greet_default() -> None:
    assert greet() == "Hello, world!"


def test_greet_named() -> None:
    assert greet("modal") == "Hello, modal!"
