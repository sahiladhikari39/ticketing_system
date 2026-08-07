/**
 * Lets this app be embedded in an iframe on the client's own website
 * without an awkward fixed-height box or a double scrollbar.
 *
 * The PARENT page (the client's Next.js site) owns the iframe element
 * and decides its width, but it has no way to know how TALL the
 * content inside actually is -- that only exists inside this app.
 * So this app measures its own height whenever it changes (route
 * navigation, a form expanding, content loading in) and tells the
 * parent via postMessage. The parent-side listener that receives this
 * lives in the client's own codebase -- see EMBED_SNIPPET.md for what
 * to hand them.
 *
 * Does nothing at all when NOT running inside an iframe (checked via
 * `window.self !== window.top`), so this has zero effect on the
 * normal, non-embedded app.
 */
export function startIframeHeightReporting() {
  if (window.self === window.top) return; // not embedded -- no-op

  const SOURCE_TAG = "soori-embed";

  function reportHeight() {
    const height = document.documentElement.scrollHeight;
    window.parent.postMessage({ source: SOURCE_TAG, height }, "*");
  }

  // Covers the common cases without any per-page wiring:
  // - ResizeObserver catches content growing/shrinking (a form
  //   expanding, a list loading in) even without a route change.
  // - popstate catches back/forward navigation.
  const observer = new ResizeObserver(reportHeight);
  observer.observe(document.body);
  window.addEventListener("popstate", reportHeight);

  // React Router navigations don't fire any native browser event, so
  // this patches the two History API methods it uses internally --
  // the standard way to detect an SPA route change from outside the
  // router itself.
  for (const method of ["pushState", "replaceState"]) {
    const original = window.history[method];
    window.history[method] = function (...args) {
      original.apply(this, args);
      // Let the new page actually render before measuring it.
      setTimeout(reportHeight, 0);
    };
  }

  reportHeight();
}
