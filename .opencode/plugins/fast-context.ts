/**
 * Fast Context Codebase Map Plugin for OpenCode.
 *
 * Injects a compact codebase map into the agent's system prompt at the
 * start of each session. The map is fetched once per session via the
 * `get_codebase_map` MCP tool and cached for the session duration.
 *
 * Auto-discovered when placed in `.opencode/plugins/`.
 */

import type { Plugin } from "@opencode-ai/plugin";

const injected = new Set<string>();

export const FastContextPlugin: Plugin = async ({ directory, $ }) => {
  return {
    "experimental.chat.system.transform": async (input, output) => {
      const sessionID = input.sessionID;
      if (!sessionID || injected.has(sessionID)) {
        return;
      }

      try {
        const proc =
          $`uv run python -c "from rag_mcp.codebase_map import get_codebase_map_text; print(get_codebase_map_text(path='.', refresh=False))"`
            .cwd(directory)
            .quiet()
            .nothrow();
        const result = await proc.text();

        if (result && !result.includes('"status": "error"')) {
          output.system.push(`# Codebase Map\n\n${result}`);
          injected.add(sessionID);
        }
      } catch (err) {
        // Silently fail — the map is a convenience, not a requirement.
        console.error("[fast-context] Failed to fetch codebase map:", err);
      }
    },
  };
};

export default FastContextPlugin;
