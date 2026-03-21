const esbuild = require("esbuild");
const fs = require("fs");
const path = require("path");

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
}).then(() => {
  // 自动同步到 VS Code 已安装的插件目录（开发便利）
  const installed = path.join(
    process.env.USERPROFILE || "",
    ".vscode", "extensions", "testpilot-ai.testpilot-ai-1.2.0",
  );
  if (fs.existsSync(installed)) {
    // 同步 extension.js
    fs.copyFileSync("out/extension.js", path.join(installed, "out", "extension.js"));
    // 同步 package.json
    fs.copyFileSync("package.json", path.join(installed, "package.json"));
    // 同步 templates/platforms/
    const srcTPl = path.join(__dirname, "templates", "platforms");
    const dstTPl = path.join(installed, "templates", "platforms");
    if (fs.existsSync(srcTPl)) {
      fs.mkdirSync(dstTPl, { recursive: true });
      for (const f of fs.readdirSync(srcTPl)) {
        fs.copyFileSync(path.join(srcTPl, f), path.join(dstTPl, f));
      }
    }
    console.log(`✅ Synced to installed extension: ${installed}`);
  }
}).catch(() => process.exit(1));
