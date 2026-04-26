import { pathToFileURL } from "node:url";
import type { Addon } from "../registry/registry.js";
import type { HookFn } from "../contract/index.js";
import { createLoaderReport } from "../contract/index.js";
import { createLoaderLogger } from "../registry/loader_logger.js";
import { discoverFiles } from "./_discover.js";

const LIFECYCLE_SUFFIXES = [".lifecycle.mjs", ".lifecycle.js"] as const;

export const ALLOW_DEFAULT_FN_SHAPE = true;

interface LifecycleModule {
  default?: unknown;
  onInit?: HookFn;
  onStartup?: HookFn;
  onShutdown?: HookFn;
}

export const lifecycleAddon: Addon = {
  name: "lifecycle",
  priority: 20,
  async run(_server, config, ctx) {
    const report = createLoaderReport("lifecycle");
    const log = createLoaderLogger("lifecycle", ctx.logger, report);
    let initCount = 0;
    let startCount = 0;
    let stopCount = 0;

    for (const dir of config.paths.lifecycles) {
      let result;
      try {
        result = await discoverFiles(dir, LIFECYCLE_SUFFIXES);
      } catch (err) {
        log.failed("discover", dir, err);
        continue;
      }
      log.scanDir(dir, result.matched.length, result.ignored.length);
      for (const p of result.ignored) log.ignored(p);
      report.discovered += result.matched.length;

      for (const file of result.matched) {
        let mod: LifecycleModule;
        try {
          mod = (await import(pathToFileURL(file).href)) as LifecycleModule;
          report.imported += 1;
          log.loaded(file);
        } catch (err) {
          log.failed("import", file, err);
          continue;
        }

        const source = (mod.default && typeof mod.default === "object")
          ? (mod.default as LifecycleModule)
          : mod;

        const defaultFn =
          typeof mod.default === "function" ? (mod.default as HookFn) : undefined;

        const hooks: string[] = [];
        if (typeof source.onInit === "function") {
          ctx.registerInitHook(source.onInit);
          initCount += 1;
          hooks.push("init");
        }
        if (typeof source.onStartup === "function") {
          ctx.registerStartupHook(source.onStartup);
          startCount += 1;
          hooks.push("startup");
        }
        if (typeof source.onShutdown === "function") {
          ctx.registerShutdownHook(source.onShutdown);
          stopCount += 1;
          hooks.push("shutdown");
        }
        if (hooks.length > 0) {
          report.registered += 1;
          log.registered(file, hooks.join("+"));
          if (ALLOW_DEFAULT_FN_SHAPE && defaultFn) {
            log.skipped(file, "default ignored: named hooks present");
          }
        } else if (ALLOW_DEFAULT_FN_SHAPE && defaultFn) {
          ctx.registerInitHook(defaultFn);
          initCount += 1;
          report.registered += 1;
          log.registered(file, "init(default)");
        } else {
          report.skipped += 1;
          log.skipped(file, "no onInit/onStartup/onShutdown export");
        }
      }
    }

    report.details = { init_hooks: initCount, startup_hooks: startCount, shutdown_hooks: stopCount };
    return report;
  },
};

export default lifecycleAddon;
