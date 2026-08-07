/**
 * Reads a video file's duration in the browser, before it's ever
 * uploaded. Loads only metadata (not the whole file) via a hidden
 * <video> element, which is fast and works for any file size.
 *
 * Client-side only -- there's no server-side duration check behind
 * this (checking video duration on the server needs a media-processing
 * library, which isn't part of this project). A determined person
 * could bypass it by calling the API directly. It stops the normal
 * case -- someone picking a video in the form -- reliably; it isn't a
 * security boundary the way the file size and type checks on the
 * backend are.
 */
export function getVideoDurationSeconds(file) {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    const url = URL.createObjectURL(file);

    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Couldn't read that video file."));
    };
    video.src = url;
  });
}

// Two very different videos share this same checking logic, at two
// very different scales:
//   - A customer's quick evidence clip at ticket creation: seconds.
//   - An engineer's full on-site recording (an Insta360-style camera):
//     up to about an hour.
export const MAX_TICKET_VIDEO_SECONDS = 10;
export const MAX_SERVICE_VIDEO_SECONDS = 60 * 60;

function formatSeconds(seconds) {
  if (seconds < 90) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)} min`;
}

/**
 * Validates a chosen video file against a duration cap. Returns null
 * when it's fine, or an error string when it isn't -- callers decide
 * what to do with that (show it, clear the selection, etc.) rather
 * than this throwing or alerting itself.
 */
export async function validateVideoDuration(file, maxSeconds) {
  if (!file) return null;
  let seconds;
  try {
    seconds = await getVideoDurationSeconds(file);
  } catch {
    // Metadata failed to load (corrupt file, unsupported codec) --
    // let the backend's own validation catch it rather than blocking
    // someone on a client-side check that couldn't actually run.
    return null;
  }
  if (seconds > maxSeconds) {
    return `This can be up to ${formatSeconds(maxSeconds)} long (this one is ${formatSeconds(seconds)}).`;
  }
  return null;
}
