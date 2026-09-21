/** 84_000_000 -> "80 MB", 2.4e9 -> "2.2 GB" */
export function formatSize(bytes: number): string {
  const mb = bytes / 1024 ** 2;
  return mb < 1024 ? `${Math.max(1, Math.round(mb))} MB` : `${(mb / 1024).toFixed(1)} GB`;
}

/** 600 -> "10 min", 10800 -> "3 hr" */
export const formatLimit = (seconds: number) =>
  seconds < 3600 ? `${Math.round(seconds / 60)} min` : `${+(seconds / 3600).toFixed(1)} hr`;
