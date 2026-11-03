"""Explicitly registered built-in plugins; no automatic loading of external code."""
from .current_time import current_time_plugin


def builtin_plugins():
    return [current_time_plugin()]
