#!/usr/bin/env node
/**
 * 客服 exe 开发模式启动器 (替代不稳定的 concurrently + wait-on 组合)
 *
 * 流程:
 *   1. 起 `next dev -p 3100`
 *   2. 轮询 http://localhost:3100/login 直到 HTTP 200
 *   3. 起 `electron .` 弹出窗口
 *   4. 任一进程退出 → 一并清理另一个
 *   5. Ctrl+C → 优雅退出两个
 *
 * 这版主要解决 Windows + PowerShell 下:
 *   - concurrently 的 npm: 简写偶发不识别
 *   - wait-on 在某些网络栈下卡住不返回
 *   - SIGINT 没传到子进程导致僵尸
 */
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 3100;
const PROBE_URL = `http://localhost:${PORT}/login`;
const PROBE_INTERVAL_MS = 500;
const PROBE_TIMEOUT_MS = 60_000;

const isWindows = process.platform === "win32";
const root = path.resolve(__dirname, "..");

function color(label, code) {
  return (line) => `\x1b[${code}m[${label}]\x1b[0m ${line}`;
}
const blue = color("NEXT", "34");
const green = color("ELECTRON", "32");

function pipePrefixed(child, paint) {
  const onChunk = (chunk) => {
    chunk
      .toString()
      .split("\n")
      .filter((l) => l.length > 0)
      .forEach((l) => process.stdout.write(paint(l) + "\n"));
  };
  child.stdout && child.stdout.on("data", onChunk);
  child.stderr && child.stderr.on("data", onChunk);
}

function runNpx(args, paint) {
  // 用 shell=true 让 npx 的 .cmd 在 Windows 上能找到
  const child = spawn(isWindows ? "npx.cmd" : "npx", args, {
    cwd: root,
    env: process.env,
    shell: isWindows,
    stdio: ["ignore", "pipe", "pipe"]
  });
  pipePrefixed(child, paint);
  return child;
}

function probeOnce() {
  return new Promise((resolve) => {
    const req = http.get(PROBE_URL, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForNext() {
  const started = Date.now();
  while (Date.now() - started < PROBE_TIMEOUT_MS) {
    if (await probeOnce()) return true;
    await new Promise((r) => setTimeout(r, PROBE_INTERVAL_MS));
  }
  return false;
}

function killChild(child) {
  if (!child || child.exitCode !== null) return;
  try {
    if (isWindows) {
      // taskkill 整棵子进程树
      spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"], {
        stdio: "ignore"
      });
    } else {
      child.kill("SIGTERM");
    }
  } catch {
    /* ignore */
  }
}

async function main() {
  console.log(blue("正在启动 Next.js dev server (3100)..."));
  const nextProc = runNpx(["next", "dev", "-p", String(PORT)], blue);

  let electronProc = null;
  let shuttingDown = false;

  const shutdown = (reason) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`\n[dev.js] shutdown: ${reason}`);
    killChild(electronProc);
    killChild(nextProc);
    process.exit(0);
  };

  nextProc.on("exit", (code) => {
    if (!shuttingDown) shutdown(`Next.js 退出 (code=${code})`);
  });

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  const ready = await waitForNext();
  if (!ready) {
    console.error(`[dev.js] ❌ Next.js 60 秒未就绪,退出`);
    shutdown("next 启动超时");
    return;
  }

  console.log(green("Next.js 已就绪,启动 Electron 窗口..."));
  electronProc = runNpx(["electron", "."], green);

  electronProc.on("exit", (code) => {
    if (!shuttingDown) shutdown(`Electron 退出 (code=${code})`);
  });
}

main().catch((err) => {
  console.error("[dev.js] fatal:", err);
  process.exit(1);
});
