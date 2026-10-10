import { api } from './api.js';
import { $, h } from './dom.js';
import {
  addMinutes,
  formatDay,
  formatPrice,
  minutesLabel,
  parseDay,
  timeOf,
  toDayString,
  weekdayOf,
} from './format.js';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const state = { shop: null, services: [], service: null, date: null, time: null, request: 0 };

function setText(selector, text) {
  $(selector).textContent = text;
}

function showError(selector, message) {
  const box = $(selector);
  box.textContent = message || '';
  box.hidden = !message;
}

function price(amount) {
  return formatPrice(amount, state.shop.currency);
}

function detailRows(booking) {
  const start = timeOf(booking.start_time);
  const end = timeOf(booking.end_time);
  const rows = [
    ['Service', booking.service.name],
    ['Date', formatDay(parseDay(booking.start_time))],
    ['Time', `${start} to ${end}`],
    ['Price', price(booking.service.price)],
    ['Name', booking.client_name],
  ];
  return rows.flatMap(([label, value]) => [h('dt', {}, label), h('dd', {}, value)]);
}

function showTodayHours() {
  const today = parseDay(state.shop.today);
  const hours = state.shop.hours.find((row) => row.weekday === weekdayOf(today));
  const text = hours && hours.is_open
    ? `Today we are open ${hours.open_time.slice(0, 5)} to ${hours.close_time.slice(0, 5)}`
    : 'Today we are closed';
  setText('#today-line', text);
}

function renderServices() {
  const list = $('#service-list');
  list.replaceChildren();
  if (!state.services.length) {
    list.append(h('p', { class: 'muted' }, 'No services are available right now.'));
    return;
  }
  for (const service of state.services) {
    list.append(
      h('label', { class: 'choice' },
        h('input', { type: 'radio', name: 'service', value: service.id }),
        h('span', { class: 'choice-body' },
          h('span', { class: 'choice-name' }, service.name),
          h('span', { class: 'choice-price' }, price(service.price)),
          h('span', { class: 'choice-meta' }, minutesLabel(service.duration_minutes)),
        ),
      ),
    );
  }
}

function renderCalendar() {
  const calendar = $('#calendar');
  calendar.replaceChildren(...WEEKDAYS.map((name) => h('span', { class: 'cal-head' }, name)));

  const first = parseDay(state.shop.today);
  for (let i = 0; i < weekdayOf(first); i++) calendar.append(h('span'));

  for (let i = 0; i <= state.shop.days_ahead; i++) {
    const day = new Date(first.getFullYear(), first.getMonth(), first.getDate() + i);
    const hours = state.shop.hours.find((row) => row.weekday === weekdayOf(day));
    const isOpen = Boolean(hours && hours.is_open);
    const month = day.toLocaleDateString('en-GB', { month: 'short' });
    calendar.append(
      h('label', { class: i === 0 ? 'day day-today' : 'day' },
        h('input', {
          type: 'radio',
          name: 'date',
          value: toDayString(day),
          disabled: !isOpen,
          'aria-label': formatDay(day),
        }),
        h('span', { class: 'day-body' },
          i === 0 || day.getDate() === 1 ? h('small', {}, month) : null,
          String(day.getDate()),
        ),
      ),
    );
  }
}

function updateSummary() {
  const ready = state.service && state.date && state.time;
  $('#step-details').hidden = !ready;
  if (!ready) return;
  const end = addMinutes(state.time, state.service.duration_minutes);
  setText(
    '#summary',
    `${state.service.name}, ${formatDay(parseDay(state.date))}, ${state.time} to ${end}, ${price(state.service.price)}`,
  );
}

async function askAssistant(event) {
  event.preventDefault();
  const text = $('#assistant-text').value.trim();
  if (text.length < 2) return;
  const button = $('#assistant-button');
  button.disabled = true;
  setText('#assistant-note', 'Looking for free times...');
  $('#assistant-list').replaceChildren();
  try {
    const answer = await api('/api/assistant', { method: 'POST', body: { text } });
    const parts = [];
    if (answer.service) parts.push(`${answer.service.name}:`);
    if (answer.suggestions.length) parts.push('pick a time below.');
    if (answer.message) parts.push(answer.message);
    setText('#assistant-note', parts.join(' '));
    $('#assistant-list').append(
      ...answer.suggestions.map((s) =>
        h('button', {
          type: 'button',
          class: 'chip chip-button',
          onclick: () => applySuggestion(answer.service.id, s.date, s.time),
        }, h('span', { class: 'chip-body' }, `${formatDay(parseDay(s.date))}, ${s.time}`)),
      ),
    );
  } catch (error) {
    setText('#assistant-note', error.message);
  } finally {
    button.disabled = false;
  }
}

async function applySuggestion(serviceId, day, time) {
  const serviceInput = document.querySelector(`input[name="service"][value="${serviceId}"]`);
  if (serviceInput) serviceInput.checked = true;
  state.service = state.services.find((service) => service.id === serviceId);
  $('#step-date').hidden = false;
  const dayInput = document.querySelector(`input[name="date"][value="${day}"]`);
  if (dayInput) dayInput.checked = true;
  state.date = day;
  await refreshTimes();
  const timeInput = document.querySelector(`input[name="time"][value="${time}"]`);
  if (timeInput) {
    timeInput.checked = true;
    state.time = time;
  }
  updateSummary();
  $('#step-details').scrollIntoView({ block: 'center' });
  $('#name').focus({ preventScroll: true });
}

async function refreshTimes() {
  if (!state.service || !state.date) return;
  const request = ++state.request;
  state.time = null;
  showError('#times-error', '');
  $('#time-list').replaceChildren();
  setText('#times-note', 'Loading free times...');
  updateSummary();

  let data;
  try {
    data = await api(`/api/slots?service_id=${state.service.id}&date=${state.date}`);
  } catch (error) {
    if (request === state.request) setText('#times-note', error.message);
    return;
  }
  if (request !== state.request) return; // a newer click already replaced this answer

  if (!data.times.length) {
    setText('#times-note', 'No free times on this day. Try another date.');
    return;
  }
  setText('#times-note', `Free times on ${formatDay(parseDay(state.date))}`);
  $('#time-list').append(
    ...data.times.map((time) =>
      h('label', { class: 'chip' },
        h('input', { type: 'radio', name: 'time', value: time }),
        h('span', { class: 'chip-body' }, time),
      ),
    ),
  );
}

function pickService(id) {
  state.service = state.services.find((service) => service.id === Number(id));
  $('#step-date').hidden = false;
  if (state.date) refreshTimes();
  else setText('#times-note', 'Pick a date to see the free times.');
  updateSummary();
}

async function submitBooking(event) {
  event.preventDefault();
  showError('#form-error', '');
  const button = $('#submit-button');
  button.disabled = true;
  try {
    const booking = await api('/api/bookings', {
      method: 'POST',
      body: {
        service_id: state.service.id,
        start_time: `${state.date}T${state.time}:00`,
        client_name: $('#name').value,
        client_phone: $('#phone').value,
      },
    });
    showConfirmation(booking);
  } catch (error) {
    if (error.status === 409) {
      // somebody was faster, show the fresh list of times
      await refreshTimes();
      showError('#times-error', error.message);
      $('#times-error').scrollIntoView({ block: 'center' });
    } else {
      showError('#form-error', error.message);
    }
  } finally {
    button.disabled = false;
  }
}

function showConfirmation(booking) {
  setText('#confirmation-code', booking.code);
  $('#confirmation-details').replaceChildren(...detailRows(booking));
  $('#booking-form').hidden = true;
  $('#confirmation').hidden = false;
  $('#manage-button').onclick = () => {
    $('#lookup-code').value = booking.code;
    $('#lookup-phone').value = booking.client_phone;
    $('#lookup-form').requestSubmit();
    $('#manage').scrollIntoView();
  };
  $('#confirmation-title').focus();
  $('#confirmation').scrollIntoView({ block: 'start' });
}

function bookAnother() {
  state.service = null;
  state.date = null;
  state.time = null;
  state.request++;
  $('#booking-form').reset();
  $('#booking-form').hidden = false;
  $('#confirmation').hidden = true;
  $('#step-date').hidden = true;
  $('#step-details').hidden = true;
  renderServices();
  renderCalendar();
  $('#book').scrollIntoView();
}

function renderFound(booking, notice) {
  const box = $('#found');
  box.hidden = false;
  box.replaceChildren(
    h('div', {},
      h('hr', { class: 'rule' }),
      notice ? h('p', { class: 'success', role: 'status' }, notice) : null,
      h('p', {},
        h('span', { class: `badge badge-${booking.status}` }, booking.status === 'active' ? 'Active' : 'Cancelled'),
        ' ',
        h('strong', {}, booking.code),
      ),
      h('dl', { class: 'details' }, ...detailRows(booking)),
      booking.status === 'active' ? cancelControls(booking) : null,
    ),
  );
  box.scrollIntoView({ block: 'nearest' });
}

function cancelControls(booking) {
  const holder = h('div', { class: 'btn-row' });
  const askButton = h('button', { class: 'btn btn-danger', type: 'button' }, 'Cancel booking');
  askButton.onclick = () => {
    holder.replaceChildren(
      h('span', {}, 'Cancel this booking?'),
      h('button', { class: 'btn btn-danger', type: 'button', onclick: () => cancelBooking(booking) }, 'Yes, cancel it'),
      h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => holder.replaceChildren(askButton) }, 'Keep it'),
    );
  };
  holder.append(askButton);
  return holder;
}

async function cancelBooking(booking) {
  try {
    const updated = await api(`/api/bookings/${encodeURIComponent(booking.code)}/cancel`, {
      method: 'POST',
      body: { client_phone: booking.client_phone },
    });
    renderFound(updated, 'Your booking is cancelled.');
    refreshTimes();
  } catch (error) {
    renderFound(booking, null);
    $('#found').prepend(h('p', { class: 'error', role: 'alert' }, error.message));
  }
}

async function lookupBooking(event) {
  event.preventDefault();
  showError('#lookup-error', '');
  $('#found').hidden = true;
  try {
    const booking = await api('/api/bookings/lookup', {
      method: 'POST',
      body: { code: $('#lookup-code').value, client_phone: $('#lookup-phone').value },
    });
    renderFound(booking);
  } catch (error) {
    showError('#lookup-error', error.message);
  }
}

async function start() {
  try {
    [state.shop, state.services] = await Promise.all([api('/api/shop'), api('/api/services')]);
  } catch (error) {
    $('#service-list').replaceChildren(h('p', { class: 'error' }, error.message));
    return;
  }
  showTodayHours();
  renderServices();
  renderCalendar();

  $('#service-list').addEventListener('change', (event) => pickService(event.target.value));
  $('#calendar').addEventListener('change', (event) => {
    state.date = event.target.value;
    refreshTimes();
  });
  $('#time-list').addEventListener('change', (event) => {
    state.time = event.target.value;
    updateSummary();
  });
  $('#booking-form').addEventListener('submit', submitBooking);
  $('#assistant-form').addEventListener('submit', askAssistant);
  $('#again-button').addEventListener('click', bookAnother);
  $('#lookup-form').addEventListener('submit', lookupBooking);
}

start();
