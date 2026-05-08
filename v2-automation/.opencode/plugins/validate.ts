import type { Plugin } from "@opencode-ai/plugin";
import { $ } from "bun";
import path from "path";

/**
 * JSON validation plugin for knowledge articles.
 *
 * Automatically validates JSON files in knowledge/articles/ when they are
 * written or edited by agents.
 */
const plugin: Plugin = {
  name: "validate-json",
  version: "1.0.0",

  hooks: {
    "tool.execute.after": async (input, context) => {
      try {
        // Only trigger on write or edit tools
        if (input.tool !== "write" && input.tool !== "edit") {
          return;
        }

        // Get file path from tool arguments
        const filePath = input.args?.file_path || input.args?.filePath;

        if (!filePath || typeof filePath !== "string") {
          return;
        }

        // Only validate JSON files in knowledge/articles/
        if (!filePath.includes("knowledge/articles/") || !filePath.endsWith(".json")) {
          return;
        }

        context.logger.info(`[validate-json] Validating ${filePath}`);

        // Execute validation script using Bun Shell API
        try {
          const result = await $`python3 hooks/validate_json.py ${filePath}`.nothrow();

          if (result.exitCode === 0) {
            context.logger.info(`[validate-json] ✓ ${filePath} passed validation`);
          } else {
            const errorOutput = result.stderr.toString() || result.stdout.toString();
            context.logger.warn(`[validate-json] ✗ ${filePath} validation failed:\n${errorOutput}`);
          }
        } catch (shellError) {
          context.logger.error(`[validate-json] Shell execution error: ${shellError}`);
        }

      } catch (error) {
        // Catch all errors to prevent blocking the agent
        context.logger.error(`[validate-json] Plugin error: ${error}`);
      }
    },
  },
};

export default plugin;
