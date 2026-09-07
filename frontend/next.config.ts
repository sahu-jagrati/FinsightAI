import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the production Docker image small (Section 28) —
  // only the traced dependency subset is copied in, not the whole node_modules.
  output: "standalone",
};

export default nextConfig;
