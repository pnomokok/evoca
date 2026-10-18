// The demo clock in the family's time zone, and how far "Next morning" moves it.

function zonedParts(date, timeZone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone, hourCycle: 'h23',
    year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric'
  }).formatToParts(date);
  const get = type => Number(parts.find(p => p.type === type)?.value);
  return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour'), minute: get('minute'), second: get('second') };
}

// UTC milliseconds of a wall-clock time in timeZone (Date.UTC rolls an overflowing day into the next month).
function zonedToUtc(year, month, day, hour, minute, timeZone) {
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  const offsetAt = (ms) => {
    const p = zonedParts(new Date(ms), timeZone);
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - ms;
  };
  // A second pass settles the offset when a DST change lies between the guess and the answer.
  const first = wall - offsetAt(wall);
  return wall - offsetAt(first);
}

// "Tue 21 Oct, 10:05"
export function formatDemoClock(iso, timeZone) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  }).formatToParts(date);
  const get = type => parts.find(p => p.type === type)?.value || '';
  return `${get('weekday')} ${get('day')} ${get('month')}, ${get('hour')}:${get('minute')}`;
}

// Hours from now to chat_time ("HH:MM") on the next local day, rounded up to a whole second so the
// scheduler sees chat time as reached; within 1-72 as POST /api/demo/advance requires. null if unknown.
export function hoursToNextMorning(nowIso, chatTime, timeZone) {
  const now = new Date(nowIso).getTime();
  const match = /^(\d{2}):(\d{2})$/.exec(chatTime || '');
  if (Number.isNaN(now) || !match || !timeZone) return null;
  const today = zonedParts(new Date(now), timeZone);
  const target = zonedToUtc(today.year, today.month, today.day + 1, Number(match[1]), Number(match[2]), timeZone);
  let hours = Math.ceil((target - now) / 1000) / 3600;
  // Chat time just after midnight, asked late in the evening: the morning after that.
  if (hours < 1) hours += 24;
  return Math.min(hours, 72);
}
