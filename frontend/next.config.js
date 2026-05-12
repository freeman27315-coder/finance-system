/** @type {import('next').NextConfig} */
const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${BACKEND_PORT}/:path*`
      }
    ];
  }
};

module.exports = nextConfig;
