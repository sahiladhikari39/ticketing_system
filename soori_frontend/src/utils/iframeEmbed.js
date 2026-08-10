/**
 * Lets this app be embedded in an iframe on the client's own website
 * without an awkward fixed-height box or a double scrollbar.
 *
 * The PARENT page (the client's Next.js site) owns the iframe element
 * and decides its width, but it has no way to know how TALL the
 * content inside actually is -- that only exists inside this app.
 * So this app measures its own height whenever it changes (route
 * navigation, a form expanding, content loading in) and tells the
 * parent via postMessage.
 *
 * ── Message contract ──────────────────────────────────────────────
 * Every message is shaped { source: 'soori-embed', type, ...payload }:
 *
 *   { type: 'height', height: number }  content height changed
 *   { type: 'unauthenticated' }         session ended; the parent
 *                                       shows a notice instead of us
 *                                       navigating the frame itself
 *
 * The parent-side listener lives in the client's own codebase --
 * gng2/components/SupportEmbed.jsx in the GNG site.
 *
 * Does nothing at all when NOT running inside an iframe (checked via
 * `window.self !== window.top`), so this has zero effect on the
 * normal, non-embedded app.
 */

const SOURCE_TAG = "soori-embed";

/**
 * Which parent origin we'll post to. postMessage's second argument is
 * a *restriction*, not a destination: "*" means any page that manages
 * to frame us can read these messages. Naming the expected origin
 * means the browser silently drops the message if we've been framed
 * by anyone else.
 *
 * Falls back to "*" when unset so local dev works without config --
 * the only thing leaked either way is a pixel height. Set
 * VITE_EMBED_PARENT_ORIGIN (e.g. https://globalnepalgroup.com) in any
 * deployed build.
 */
const PARENT_ORIGIN = import.meta.env.VITE_EMBED_PARENT_ORIGIN || "*";

export function isEmbedded() {
  // Cross-origin framing makes window.top access throw in some
  // browsers rather than returning a value, and "we couldn't even
  // look" is itself proof we're framed by another origin.
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

function post(message) {
  if (!isEmbedded()) return;
  window.parent.postMessage({ source: SOURCE_TAG, ...message }, PARENT_ORIGIN);
}

/**
 * Tells the host page the session is over, INSTEAD of this app
 * redirecting itself to /login. A redirect inside the frame renders
 * our standalone login screen in a box on someone else's page, which
 * reads as a broken embed; the parent can present it properly.
 */
export function notifyParentUnauthenticated() {
  post({ type: "unauthenticated" });
}

/**
 * How long to keep re-announcing our height after boot, and how often.
 *
 * Why this exists: the host embeds us in server-rendered HTML, so the
 * browser starts loading this iframe while parsing their page -- but
 * their listener only attaches once THEIR framework has downloaded and
 * hydrated. This app is small and boots first, so a single height
 * broadcast at startup routinely arrives before anyone is listening,
 * and ResizeObserver then stays silent because the content has already
 * settled. The host sees nothing and concludes we're offline.
 *
 * Confirmed by console ordering against the GNG site: both of our
 * posts landed before their "listener attached" line.
 *
 * A host implementing the handshake below (replying to our messages
 * with a 'host-ready' ping) stops this early -- the interval is the
 * fallback that makes the embed work even against a host that only
 * listens and never pings.
 */
const ANNOUNCE_INTERVAL_MS = 400;
const ANNOUNCE_WINDOW_MS = 8000;

export function startIframeHeightReporting() {
  if (!isEmbedded()) return; // not embedded -- no-op

  /**
   * Reports how much room this app needs, which is only ever "more
   * than I've been given" -- never less.
   *
   * That asymmetry is deliberate, and worth understanding before
   * anyone tries to make it shrink. Every screen here is
   * `min-height: 100vh`, and inside a frame `100vh` IS the frame's
   * height, so a short screen genuinely fills whatever it's given.
   * On top of that, documentElement.scrollHeight is floored at the
   * viewport height by definition. Both effects point the same way:
   * this number can exceed the frame's height, but never fall below
   * it.
   *
   * Two attempts to defeat that both failed and are recorded here so
   * they aren't retried: neutralising `min-height` collapsed the flex
   * column that centres the login card (it reported 115px), and
   * measuring `body` instead of documentElement hit the same collapse.
   *
   * So the host owns the baseline height and this only ever asks to
   * grow past it. The `navigate` message below is what lets the host
   * drop back to its baseline when moving to a shorter screen.
   */
  function reportHeight() {
    post({ type: "height", height: document.documentElement.scrollHeight });
  }

  // The host pings us as soon as its listener is live. That's the
  // authoritative "someone is listening now" signal, so answer it
  // immediately and stop the blind retry loop.
  let announceTimer = null;
  function stopAnnouncing() {
    if (announceTimer !== null) {
      clearInterval(announceTimer);
      announceTimer = null;
    }
  }

  window.addEventListener("message", (event) => {
    // Only the page that framed us can be the host. We don't check
    // origin here -- the host's origin isn't known to us and a
    // spoofed ping achieves nothing beyond making us re-send a height
    // we already broadcast.
    if (event.data?.source !== "soori-embed-host") return;
    if (event.data.type === "host-ready") {
      stopAnnouncing();
      reportHeight();
    }
  });

  announceTimer = setInterval(reportHeight, ANNOUNCE_INTERVAL_MS);
  setTimeout(stopAnnouncing, ANNOUNCE_WINDOW_MS);

  // Covers the common cases without any per-page wiring:
  // - ResizeObserver catches content growing/shrinking (a form
  //   expanding, a list loading in) even without a route change.
  // - popstate catches back/forward navigation.
  const observer = new ResizeObserver(reportHeight);
  observer.observe(document.body);
  window.addEventListener("popstate", onNavigate);

  /**
   * Announces a route change BEFORE re-measuring.
   *
   * Because reportHeight can only ever ask to grow, leaving a long
   * ticket list for the short new-ticket form would otherwise strand
   * the frame at the taller size with dead space below it. Telling the
   * host first lets it drop back to its baseline; the height that
   * follows a moment later then grows it again only if the new screen
   * genuinely needs it.
   */
  function onNavigate() {
    post({ type: "navigate" });
    setTimeout(reportHeight, 0);
  }

  // React Router navigations don't fire any native browser event, so
  // this patches the two History API methods it uses internally --
  // the standard way to detect an SPA route change from outside the
  // router itself.
  for (const method of ["pushState", "replaceState"]) {
    const original = window.history[method];
    window.history[method] = function (...args) {
      original.apply(this, args);
      // Let the new page actually render before measuring it.
      onNavigate();
    };
  }

  reportHeight();
}
