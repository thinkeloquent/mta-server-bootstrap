from __future__ import annotations

import inspect

from fastapi_server.bootstrap.contract import create_loader_report
from fastapi_server.bootstrap.registry.registry import Addon
from fastapi_server.bootstrap.registry.loader_logger import create_loader_logger
from fastapi_server.bootstrap.addons._discover import discover_files, import_file

_SUFFIXES = (".lifecycle.py",)

ALLOW_DEFAULT_FN_SHAPE = True


def _run(_server, config, ctx):
    report = create_loader_report("lifecycle")
    log = create_loader_logger("lifecycle", ctx.logger, report)
    init_count = 0
    start_count = 0
    stop_count = 0

    for d in config.paths.lifecycles:
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
                mod = import_file(file, module_name_prefix="polyglot_lifecycle")
                report.imported += 1
                log.loaded(file)
            except Exception as err:  # noqa: BLE001
                log.failed("import", file, err)
                continue

            on_init = getattr(mod, "on_init", None)
            on_startup = getattr(mod, "on_startup", None)
            on_shutdown = getattr(mod, "on_shutdown", None)
            default_fn = getattr(mod, "default", None) or getattr(mod, "main", None)

            hooks = []
            if callable(on_init):
                ctx.register_init_hook(on_init)
                init_count += 1
                hooks.append("init")
            if callable(on_startup):
                ctx.register_startup_hook(on_startup)
                start_count += 1
                hooks.append("startup")
            if callable(on_shutdown):
                ctx.register_shutdown_hook(on_shutdown)
                stop_count += 1
                hooks.append("shutdown")

            if hooks:
                report.registered += 1
                log.registered(file, "+".join(hooks))
                if ALLOW_DEFAULT_FN_SHAPE and callable(default_fn):
                    log.skipped(file, "default ignored: named hooks present")
            elif ALLOW_DEFAULT_FN_SHAPE and callable(default_fn):
                if inspect.iscoroutinefunction(default_fn):
                    ctx.register_init_hook(default_fn)
                else:
                    sync_fn = default_fn

                    async def _wrapped(*args, _fn=sync_fn, **kwargs):
                        return _fn(*args, **kwargs)

                    ctx.register_init_hook(_wrapped)
                init_count += 1
                report.registered += 1
                log.registered(file, "init(default)")
            else:
                report.skipped += 1
                log.skipped(file, "no on_init/on_startup/on_shutdown export")

    report.details = {
        "init_hooks": init_count,
        "startup_hooks": start_count,
        "shutdown_hooks": stop_count,
    }
    return report


lifecycle_addon = Addon(name="lifecycle", priority=20, run=_run)
