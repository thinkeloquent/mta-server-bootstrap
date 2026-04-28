from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from fastapi_server.bootstrap.contract import (
    BootstrapConfig,
    HookCollector,
    LoaderReport,
    ResolvedBootstrapConfig,
    merge_config,
)
from fastapi_server.bootstrap.registry.ctx import Logger, StdoutLogger, create_context
from fastapi_server.bootstrap.registry.registry import Addon, Registry


@dataclass
class SetupOptions:
    base_dir: Optional[str] = None
    defaults: Dict[str, Any] = field(default_factory=dict)
    logger: Optional[Logger] = None


async def setup(
    adapter: Any,
    addons: Union[List[Addon], Registry],
    user_config: Union[Dict[str, Any], BootstrapConfig],
    opts: Optional[SetupOptions] = None,
) -> Any:
    opts = opts or SetupOptions()
    logger: Logger = opts.logger or StdoutLogger()
    base_dir = opts.base_dir or os.getcwd()

    config: ResolvedBootstrapConfig = merge_config(opts.defaults or {}, user_config, base_dir)

    registry = addons if isinstance(addons, Registry) else _to_registry(addons)

    server = adapter.create_server(config)
    if inspect.isawaitable(server):
        server = await server

    adapter.decorate(server, "_config", config)

    hooks = HookCollector()
    ctx = create_context(adapter, config, hooks, logger)

    reports: Dict[str, LoaderReport] = await registry.run_all(server, config, ctx)
    adapter.decorate(server, "_loader_reports", reports)

    for name, r in reports.items():
        if r.errors:
            logger.warn(
                f"addon {name}: {len(r.errors)} error(s); discovered={r.discovered} registered={r.registered}"
            )
            for i, e in enumerate(r.errors):
                where = f" {e.path}" if e.path else ""
                logger.error(f"  addon {name} error[{i}] step={e.step}{where}: {e.error}")
        else:
            logger.info(
                f"addon {name}: discovered={r.discovered} registered={r.registered} skipped={r.skipped}"
            )

    if config.initial_state:
        adapter.attach_request_state(server, config.initial_state)

    await _run_init_hooks(server, config, hooks.init, logger)

    adapter.schedule_hooks(server, {"startup": hooks.startup, "shutdown": hooks.shutdown}, config)
    adapter.register_graceful_shutdown(server)

    return server


def _to_registry(addons: List[Addon]) -> Registry:
    reg = Registry()
    for a in addons:
        reg.register(a)
    return reg


async def _run_init_hooks(server: Any, config: ResolvedBootstrapConfig, inits: list, logger: Logger) -> None:
    for fn in inits:
        label = getattr(fn, "__name__", "anonymous")
        try:
            result = fn(server, config)
            if inspect.isawaitable(result):
                await result
            logger.debug(f"init hook '{label}' completed")
        except Exception as err:  # noqa: BLE001
            logger.error(f"init hook '{label}' failed:", err)
