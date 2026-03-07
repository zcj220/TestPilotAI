const esbuild = require("esbuild");

esbuild.build({
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "out/extension.js",
  external: ["vscode"],   // vscode API 由宿主提供，不打包
  format: "cjs",
  platform: "node",
  target: "node16",
  sourcemap: true,
  minify: false,
}).catch(() => process.exit(1));
