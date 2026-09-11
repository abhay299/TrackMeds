// The device's own time zone is the source of truth for "today" and for how
// times are shown — the same zone the API stores against.
export const deviceTz = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

/** UTC bounds of a local calendar day, as the API's /doses window expects. */
export function localDayWindow(date = new Date()): { from: string; to: string } {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { from: start.toISOString(), to: end.toISOString() };
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
export const formatTime = (iso: string): string => timeFmt.format(new Date(iso));
export const formatDay = (date: Date): string => dayFmt.format(date);

/** "in 2 hours" / "3 hours ago" — used on due/missed doses.
 * Written by hand rather than with Intl.RelativeTimeFormat, which Hermes does
 * not ship. */
export function formatRelative(iso: string, now = new Date()): string {
  const mins = Math.round((new Date(iso).getTime() - now.getTime()) / 60000);
  const ago = mins < 0;
  const say = (n: number, unit: string) => {
    const plural = `${n} ${unit}${n === 1 ? '' : 's'}`;
    return ago ? `${plural} ago` : `in ${plural}`;
  };
  const m = Math.abs(mins);
  if (m < 1) return 'now';
  if (m < 60) return say(m, 'minute');
  const hours = Math.round(m / 60);
  if (hours < 24) return say(hours, 'hour');
  return say(Math.round(hours / 24), 'day');
}
