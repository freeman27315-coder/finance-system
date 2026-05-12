/** @type {import('next').NextConfig} */
const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const nextConfig = {
  // Electron 打包用静态导出
  output: process.env.NEXT_EXPORT === "1" ? "export" : undefined,
  // 开发时把 /api/* 转给后端 (BACKEND_PORT env 默认 8000)
  async rewrites() {
    if (process.env.NEXT_EXPORT === "1") return [];
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${BACKEND_PORT}/:path*`
      }
    ];
  },
  // 静态导出时 next/image 无优化
  images: {
    unoptimized: true
  }
};

module.exports = nextConfig;
