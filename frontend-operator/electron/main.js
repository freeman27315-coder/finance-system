// Electron 主进程入口 (CEO 2026-05-12: XBOX 客服销售系统)
//
// 开发模式: 加载 http://localhost:3100 (Next.js dev server)
// 生产模式: 加载 file://.../out/index.html (Next.js export)
const { app, BrowserWindow, shell } = require("electron");
const path = require("path");

const isDev = !app.isPackaged;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 720,
    title: "XBOX 客服销售系统",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // 开发时允许 CORS 给后端 localhost:8000 用
      webSecurity: !isDev
    }
  });

  if (isDev) {
    // 开发: Next.js dev server
    win.loadURL("http://localhost:3100/login");
    // win.webContents.openDevTools({ mode: "detach" });
  } else {
    // 生产: 静态导出的 index.html
    win.loadFile(path.join(__dirname, "..", "out", "login.html"));
  }

  // 外链(如 Microsoft 登录页)在默认浏览器打开,不在 Electron 内
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
