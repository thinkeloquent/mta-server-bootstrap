import type {
  BootstrapConfig,
  HookCollector,
  HookFn,
  LoaderReports,
  ResolvedBootstrapConfig,
} from "../contract/index.js";
import { mergeConfig } from "../contract/index.js";
import type { RuntimeAdapter } from "../adapters/adapter.js";
import type { Addon, Registry } from "../registry/registry.js";
import { Registry as RegistryClass } from "../registry/registry.js";
import { createContext, consoleLogger } from "../registry/ctx.js";
import type { Logger } from "../registry/ctx.js";

export interface SetupOptions {
  baseDir?: string;
  defaults?: BootstrapConfig;
  logger?: Logger;
}

export async function setup<Server>(
  adapter: RuntimeAdapter<Server>,
  addons: Addon<Server>[] | Registry<Server>,
  userConfig: BootstrapConfig,
  opts: SetupOptions = {},
): Promise<Server> {
  const logger = opts.logger ?? consoleLogger;
  const baseDir = opts.baseDir ?? process.cwd();
  const defaults = opts.defaults ?? {};

  const config: ResolvedBootstrapConfig = mergeConfig(defaults, userConfig, baseDir);

  const registry = addons instanceof RegistryClass ? addons : toRegistry(addons);

  const server = await adapter.createServer(config);

  adapter.decorate(server, "_config", config);

  const hooks: HookCollector<Server> = { init: [], startup: [], shutdown: [] };
  const ctx = createContext(adapter, config, hooks, logger);

  const reports: LoaderReports = await registry.runAll(server, config, ctx);
  adapter.decorate(server, "_loaderReports", reports);

  for (const name of Object.keys(reports)) {
    const r = reports[name]!;
    if (r.errors.length > 0) {
      logger.warn(
        `addon ${name}: ${r.errors.length} error(s); discovered=${r.discovered} registered=${r.registered}`,
      );
      for (const [i, e] of r.errors.entries()) {
        const where = e.path ? ` ${e.path}` : "";
        logger.error(`  addon ${name} error[${i}] step=${e.step}${where}: ${e.error}`);
      }
    } else {
      logger.info(
        `addon ${name}: discovered=${r.discovered} registered=${r.registered} skipped=${r.skipped}`,
      );
    }
  }

  if (config.initial_state && Object.keys(config.initial_state).length > 0) {
    adapter.attachRequestState(server, config.initial_state);
  }

  await runInitHooks(server, config, hooks.init, logger);

  adapter.scheduleHooks(server, { startup: hooks.startup, shutdown: hooks.shutdown }, config);
  adapter.registerGracefulShutdown(server);

  return server;
}

function toRegistry<Server>(addons: Addon<Server>[]): Registry<Server> {
  const reg = new RegistryClass<Server>();
  for (const a of addons) reg.register(a);
  return reg;
}

async function runInitHooks<Server>(
  server: Server,
  config: ResolvedBootstrapConfig,
  inits: HookFn<Server>[],
  logger: Logger,
): Promise<void> {
  for (const fn of inits) {
    const label = (fn as { name?: string }).name || "anonymous";
    try {
      await fn(server, config);
      logger.debug(`init hook '${label}' completed`);
    } catch (err) {
      logger.error(`init hook '${label}' failed:`, err);
    }
  }
}
