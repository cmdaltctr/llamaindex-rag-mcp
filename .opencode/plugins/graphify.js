// graphify OpenCode plugin
// Detects when the knowledge graph exists so the agent session knows it's
// available. The actual "use graphify query before grepping" guidance lives
// in AGENTS.md (the graphify section) — no need to inject a runtime echo
// banner that pollutes bash stdout.
//
// This plugin is intentionally a no-op for now. It exists as a hook point
// for future smarter logic (e.g. suggesting graphify query when the agent
// runs grep/find/ls against source files the graph already indexes).
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  const graphExists = existsSync(join(directory, "graphify-out", "graph.json"));

  return {
    "tool.execute.before": async (_input, _output) => {
      // No-op: graphify guidance is in AGENTS.md, not injected into stdout.
      // graphExists is available if future logic needs it.
      void graphExists;
    },
  };
};
