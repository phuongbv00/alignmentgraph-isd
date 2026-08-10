"""Marks the server tests as a package.

Without this, `tests/server/conftest.py` is imported under the bare module name
`conftest` and shadows `tests/conftest.py`, breaking the `from conftest import
FakeChatModel` that the core tests rely on.
"""
