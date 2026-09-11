// A schedule as one human line: "Daily · 8:00 AM, 8:00 PM", "Every 2 days · 9:00 AM".
import type { Schedule } from '@/api/types';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function times(schedule: Schedule): string {
  return schedule.times_of_day
    .map((t) => {
      const [h, m] = t.split(':').map(Number);
      const d = new Date();
      d.setHours(h, m, 0, 0);
      return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(d);
    })
    .join(', ');
}

export function scheduleSummary(schedule: Schedule): string {
  const dose = `${schedule.dose_amount} ${schedule.dose_unit}`;
  switch (schedule.kind) {
    case 'daily':
      return `Daily · ${times(schedule)} · ${dose}`;
    case 'weekly': {
      const days = schedule.days_of_week.map((d) => DAYS[d]).join(', ');
      return `${days} · ${times(schedule)} · ${dose}`;
    }
    case 'every_n_days':
      return `Every ${schedule.interval} days · ${times(schedule)} · ${dose}`;
    case 'every_n_hours':
      return `Every ${schedule.interval} h · ${dose}`;
    case 'as_needed':
      return `As needed · ${dose}`;
    default:
      return dose;
  }
}
