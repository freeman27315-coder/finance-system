// Preload 脚本: 给渲染进程暴露受控的 API
// 目前 P0 阶段渲染进程只用 fetch 直连后端,不需要 IPC,所以这里几乎空。
// PR C 时如需 "复制密码到剪贴板" / "打开 Microsoft 登录页" 等本机能力会加 IPC。
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("operatorExe", {
  version: "0.1.0",
  isElectron: true
});
