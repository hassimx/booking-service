const pad = (n) => String(n).padStart(2, '0');

// "2026-10-09" or "2026-10-09T10:00:00" -> local Date at midnight
export function parseDay(text) {
  const [year, month, day] = text.slice(0, 10).split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function toDayString(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDay(date) {
  return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

export function formatPrice(price, currency) {
  return `${price.toLocaleString('en-US')} ${currency}`;
}

// "2026-10-09T10:00:00" -> "10:00"
export function timeOf(text) {
  return text.slice(11, 16);
}

export function addMinutes(time, minutes) {
  const [hours, mins] = time.split(':').map(Number);
  const total = hours * 60 + mins + minutes;
  return `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
}

// "+77000000001" -> "+7 700 000 00 01", other numbers stay as they are
export function formatPhone(phone) {
  const match = /^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/.exec(phone);
  return match ? `+7 ${match[1]} ${match[2]} ${match[3]} ${match[4]}` : phone;
}

export function minutesLabel(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

// monday is 0, like in the api
export function weekdayOf(date) {
  return (date.getDay() + 6) % 7;
}
