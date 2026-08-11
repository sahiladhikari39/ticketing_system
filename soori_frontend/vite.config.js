import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * BASE PATH
 *
 * This app is served under /support on the client's website, not at a
 * domain root. `base` is what puts that prefix into every asset URL
 * the build emits.
 *
 * Without it the built index.html asks for /assets/index-abc.js, and
 * on the client's domain that request hits THEIR site, which knows
 * nothing about it -- so the page loads and then renders nothing, with
 * only 404s in the network tab to explain why.
 *
 * It applies to the dev server too, so `npm run dev` serves at
 * http://localhost:5173/support/ rather than /. That's deliberate:
 * the path layout then matches production, and the host site's proxy
 * can forward the path through unchanged instead of needing different
 * rules per environment.
 *
 * Override with VITE_BASE_PATH=/ to run this standalone at a root.
 */
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || "/support/",
  server: {
    port: 5173,
  },
});
