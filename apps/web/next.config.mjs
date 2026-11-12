const API_URL = process.env.API_URL || "http://localhost:8000";
export default {
  async rewrites() { return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }]; },
};
