import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The dashboard never exposes SUPABASE_SERVICE_ROLE_KEY to the browser —
  // only NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are
  // bundled. Server-side reads use the service-role key via the API route.
};

export default nextConfig;
