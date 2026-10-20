// Keep dev dependency bundles proportional to the icons the application imports.
// Production builds already tree-shake these packages; Vite's dev entrypoints
// otherwise preserve every icon export (several MB per icon family).
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import ts from "typescript";
import type { Plugin, ViteDevServer } from "vite";

type IconImports = Map<string, Set<string> | null>;
const ICON_PACKAGE = /^(?:@tabler\/icons-react|react-icons\/[a-z0-9]+)$/;
const SOURCE_FILE = /\.[cm]?[jt]sx?$/;

export function collectIconImports(source: string): IconImports {
  const imports: IconImports = new Map();
  if (!source.includes("react-icons") && !source.includes("@tabler/icons-react")) return imports;
  const file = ts.createSourceFile(
    "icons.tsx",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const add = (pack: string, names: string[] | null) => {
    if (!ICON_PACKAGE.test(pack) || imports.get(pack) === null) return;
    if (names === null) {
      imports.set(pack, null);
      return;
    }
    const selected = imports.get(pack) ?? new Set<string>();
    names.forEach((name) => selected.add(name));
    if (selected.size) imports.set(pack, selected);
  };
  const visit = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const clause = node.importClause;
      if (clause?.isTypeOnly) return;
      const bindings = clause?.namedBindings;
      add(
        node.moduleSpecifier.text,
        clause && !clause.name && bindings && ts.isNamedImports(bindings)
          ? bindings.elements
              .filter((entry) => !entry.isTypeOnly)
              .map((entry) => (entry.propertyName ?? entry.name).text)
          : null,
      );
    } else if (
      ts.isExportDeclaration(node) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      if (node.isTypeOnly) return;
      const bindings = node.exportClause;
      add(
        node.moduleSpecifier.text,
        bindings && ts.isNamedExports(bindings)
          ? bindings.elements
              .filter((entry) => !entry.isTypeOnly)
              .map((entry) => (entry.propertyName ?? entry.name).text)
          : null,
      );
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      const argument = node.arguments[0];
      if (argument && ts.isStringLiteral(argument)) add(argument.text, null);
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return imports;
}

export function trimIconExports(code: string, id: string, imports: IconImports): string | null {
  const normalized = id.replaceAll("\\", "/");
  const reactPack = normalized.match(/\/react-icons\/([a-z0-9]+)\/index\.mjs$/)?.[1];
  const tabler = normalized.endsWith("/@tabler/icons-react/dist/esm/tabler-icons-react.mjs");
  const selected = imports.get(
    reactPack ? `react-icons/${reactPack}` : tabler ? "@tabler/icons-react" : "",
  );
  if (!selected) return null; // Namespace/dynamic imports retain the full public API.
  if (reactPack) {
    return code.replace(/export\s+function\s+([\w$]+)\b/g, (declaration, name: string) =>
      selected.has(name) ? declaration : declaration.replace(/^export\s+/, ""),
    );
  }
  return code.replace(
    /export\s*\{([^}]+)\}(\s*from\s*["'][^"']+["'])?\s*;?/g,
    (_declaration, bindings: string, from: string | undefined) => {
      const retained = bindings.split(",").filter((binding) => {
        const exported = binding
          .trim()
          .split(/\s+as\s+/)
          .at(-1);
        return exported !== undefined && selected.has(exported);
      });
      return retained.length ? `export {${retained.join(",")}}${from ?? ""};` : "";
    },
  );
}

function mergeImports(files: Map<string, IconImports>): IconImports {
  const result: IconImports = new Map();
  for (const imports of files.values()) {
    for (const [pack, names] of imports) {
      if (result.get(pack) === null) continue;
      if (names === null) {
        result.set(pack, null);
        continue;
      }
      const selected = result.get(pack) ?? new Set<string>();
      names.forEach((name) => selected.add(name));
      result.set(pack, selected);
    }
  }
  return result;
}

function fingerprint(imports: IconImports): string {
  const entries = [...imports]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([pack, names]) => [pack, names ? [...names].sort() : null]);
  return createHash("sha256").update(JSON.stringify(entries)).digest("hex").slice(0, 12);
}

export async function createIconDependencyOptimizer(sourceRoot: string) {
  const files = new Map<string, IconImports>();
  const read = async (file: string) => {
    const imports = collectIconImports(await fs.readFile(file, "utf8"));
    if (imports.size) files.set(file, imports);
    else files.delete(file);
  };
  const scan = async (directory: string): Promise<void> => {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    await Promise.all(
      entries.map((entry) => {
        const file = path.join(directory, entry.name);
        return entry.isDirectory()
          ? scan(file)
          : SOURCE_FILE.test(entry.name)
            ? read(file)
            : undefined;
      }),
    );
  };
  await scan(sourceRoot);
  const imports = mergeImports(files);
  const signature = fingerprint(imports);
  const optimizerPlugin = {
    name: `arkos-icon-exports-${signature}`,
    transform(code: string, id: string) {
      return trimIconExports(code, id, imports);
    },
  };
  const watchPlugin = {
    name: `arkos-icon-inventory-${signature}`,
    apply: "serve",
    configureServer(server: ViteDevServer) {
      // Adding/removing an icon must invalidate the optimized entrypoint. Normal
      // component edits keep Fast Refresh; only a changed icon inventory restarts Vite.
      let updates = Promise.resolve();
      let restarting = false;
      const changed = (event: string, file: string) => {
        const relative = path.relative(sourceRoot, file);
        if (relative.startsWith("..") || path.isAbsolute(relative) || !SOURCE_FILE.test(file))
          return;
        if (!["add", "change", "unlink"].includes(event)) return;
        updates = updates
          .then(async () => {
            if (restarting) return;
            if (event === "unlink") files.delete(file);
            else await read(file);
            if (fingerprint(mergeImports(files)) !== signature) {
              restarting = true;
              await server.restart();
            }
          })
          .catch((error: unknown) =>
            server.config.logger.error(`Icon dependency refresh failed: ${String(error)}`),
          );
      };
      server.watcher.on("all", changed);
      server.httpServer?.once("close", () => server.watcher.off("all", changed));
    },
  } satisfies Plugin;
  return { optimizerPlugin, watchPlugin, packages: [...imports.keys()] };
}
