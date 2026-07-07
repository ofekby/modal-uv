"""Example main module."""


def greet(name: str = "world") -> str:
    return f"Hello, {name}!"


def main() -> None:
    print(greet())
