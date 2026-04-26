from __future__ import annotations

import inspect

from fastapi_server.bootstrap.contract import create_loader_report
from fastapi_server.bootstrap.registry.registry import Addon
from fastapi_server.bootstrap.registry.loader_logger import create_loader_logger
from fastapi_server.bootstrap.addons._discover import discover_files, import_file

_SUFFIXES = (".env.py",)

ALLOW_DEFAULT_FN_SHAPE = True


async def _run(_server, config, ctx):
    report = create_loader_report("environment")
    log = create_loader_logger("environment", ctx.logger, report)

    for d in config.paths.environment:
        try:
            result = discover_files(d, _SUFFIXES)
        except Exception as err:  # noqa: BLE001
            log.failed("discover", d, err)
            continue
        log.scan_dir(d, len(result.matched), len(result.ignored))
        for p in result.ignored:
            log.ignored(p)
        report.discovered += len(result.matched)

        for file in result.matched:
            try:
                mod = import_file(file, module_name_prefix="polyglot_env")
                report.imported += 1
                log.loaded(file)
            except Exception as err:  # noqa: BLE001
                log.failed("import", file, err)
                continue

            default_fn = getattr(mod, "default", None) or getattr(mod, "main", None)
            if ALLOW_DEFAULT_FN_SHAPE and callable(default_fn):
                try:
                    result_value = default_fn(_server, config)
                    if inspect.isawaitable(result_value):
                        await result_value
                    report.registered += 1
                except Exception as err:  # noqa: BLE001
                    log.failed("default-call", file, err)
                    continue
            else:
                report.registered += 1
    return report


environment_addon = Addon(name="environment", priority=10, run=_run)
