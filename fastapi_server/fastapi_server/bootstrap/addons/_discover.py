from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import List, Tuple

from fastapi_server.bootstrap.contract import sort_by_numeric_prefix


@dataclass
class DiscoverResult:
    matched: List[str] = field(default_factory=list)
    ignored: List[str] = field(default_factory=list)


def find_matching_files(directory: str, suffixes: Tuple[str, ...]) -> List[str]:
    return discover_files(directory, suffixes).matched


def discover_files(directory: str, suffixes: Tuple[str, ...]) -> DiscoverResult:
    if not os.path.isdir(directory):
        return DiscoverResult()
    matched: List[str] = []
    ignored: List[str] = []
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            ignored.append(full)
            continue
        if name.endswith(suffixes):
            matched.append(full)
        else:
            ignored.append(full)
    return DiscoverResult(matched=sort_by_numeric_prefix(matched), ignored=ignored)


def import_file(path: str, module_name_prefix: str = "polyglot_dyn") -> ModuleType:
    base = os.path.splitext(os.path.basename(path))[0].replace("-", "_").replace(".", "_")
    parent_name = module_name_prefix
    module_name = f"{parent_name}.{base}"

    # Register a synthetic parent package so relative imports inside `path`
    # (e.g. `from ._di import …`) resolve siblings via the parent's
    # `__path__`. Without this, exec_module raises
    # "No module named '<module_name_prefix>'" on the first relative import.
    dir_path = os.path.dirname(os.path.abspath(path))
    parent = sys.modules.get(parent_name)
    if parent is None:
        parent = ModuleType(parent_name)
        parent.__path__ = [dir_path]
        sys.modules[parent_name] = parent
    else:
        existing = list(getattr(parent, "__path__", []))
        if dir_path not in existing:
            existing.append(dir_path)
            parent.__path__ = existing

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so circular relative imports (rare, but legal)
    # see a partially-initialized module instead of an ImportError.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
