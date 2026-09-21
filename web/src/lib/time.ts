/** Shortest clip the timeline allows, in seconds. */
export const MIN_CLIP = 0.5;

export const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

/** Snap to tenths of a second, the precision the UI works in. */
export const round1 = (seconds: number) => Math.round(seconds * 10) / 10;

/** 67.3 -> "1:07.3", 3725 -> "1:02:05.0" */
export function formatTime(seconds: number): string {
  const tenths = Math.round(Math.max(0, seconds) * 10);
  const whole = Math.floor(tenths / 10);
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = `${String(whole % 60).padStart(2, "0")}.${tenths % 10}`;
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** Same as formatTime without the tenths: used for tick labels and the elapsed timer. */
export const formatClock = (seconds: number) => formatTime(seconds).slice(0, -2);

/** Accepts "67.3", "1:07.3" or "1:02:05"; returns null for anything else. */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(":");
  if (parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.reduce((total, p) => total * 60 + Number(p), 0);
}
