import type { NextConfig } from "next";

const apiOrigin =
  process.env.SHELBYTRAIN_API_ORIGIN ??
  (process.env.VERCEL ? "https://shelbytrain.onrender.com" : "http://127.0.0.1:8000");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
