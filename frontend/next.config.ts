import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  // 启用 Turbopack 加速开发编译 (Next.js 15 正式配置)
  turbopack: {},
};

export default nextConfig;
