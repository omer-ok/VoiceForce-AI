
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Optimized production Docker deployment
  output: "standalone",

  experimental: {
    agentFeedback: true,
  },

  // Next.js 16 caching and partial prefetching
  cacheComponents: true,
  partialPrefetching: true,

  // Tailwind CSS Turbopack configuration
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
