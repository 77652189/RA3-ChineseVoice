"""Import ra3cv.py (project root, not a package) from tools."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    spec = importlib.util.spec_from_file_location('ra3cv', os.path.join(ROOT, 'ra3cv.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
