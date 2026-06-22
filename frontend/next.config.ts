import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin the workspace root to this app so the standalone build always emits
  // `server.js` at the top of `.next/standalone` (the path the Dockerfile runs).
  // Without this, a stray lockfile elsewhere can nest the output under a subdir.
  outputFileTracingRoot: path.join(__dirname),
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
