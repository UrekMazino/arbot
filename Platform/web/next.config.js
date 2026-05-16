/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    // API_BACKEND_URL is a server-side-only env var (no NEXT_PUBLIC_ prefix).
    // Set it to the API server's internal address so the Next.js server proxies
    // /api/v2/* requests on behalf of the browser, eliminating cross-origin issues.
    // Example: API_BACKEND_URL=http://api:8080  (Docker internal DNS)
    //          API_BACKEND_URL=http://127.0.0.1:8080  (local dev without Docker)
    const backend = (process.env.API_BACKEND_URL || "").trim();
    if (!backend) return [];
    return [
      {
        source: "/api/v2/:path*",
        destination: `${backend}/api/v2/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
