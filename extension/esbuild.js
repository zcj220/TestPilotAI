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
  // 自动同步到所有已安装的 IDE 扩展目录（开发便利）
  const home = process.env.USERPROFILE || "";
  const extName = "testpilot-ai.testpilot-ai-1.2.8";
  const ideDirs = [
    path.join(home, ".vscode", "extensions", extName),
    path.join(home, ".trae", "extensions", extName),
    path.join(home, ".cursor", "extensions", extName),
    path.join(home, ".windsurf", "extensions", extName),
    path.join(home, ".vscodium", "extensions", extName),
    path.join(home, ".vscode-insiders", "extensions", extName),
  ];

  function syncToDir(installed) {
    // 同步 extension.js
    const outDir = path.join(installed, "out");
    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
    fs.copyFileSync("out/extension.js", path.join(outDir, "extension.js"));
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
  }

  let synced = 0;
  for (const dir of ideDirs) {
    if (fs.existsSync(dir)) {
      try {
        syncToDir(dir);
        console.log(`✅ Synced to: ${dir}`);
        synced++;
      } catch (e) {
        console.log(`⚠️ Failed to sync to ${dir}: ${e.message}`);
      }
    }
  }
  if (synced === 0) {
    console.log("⚠️ No installed extension directories found");
  }
}).catch(() => process.exit(1));
