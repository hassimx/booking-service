import { api, ApiError } from './api.js';
import { $, h } from './dom.js';
import { formatPhone, formatPrice, minutesLabel, parseDay, timeOf, toDayString } from './format.js';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const state = { shop: null, day: null, status: 'active', services: [], editing: null };

function price(amount) {
  return formatPrice(amount, state.shop.currency);
}

function showError(message) {
  const box = $('#admin-error');
  box.textContent = message || '';
  box.hidden = !message;
}

let flashTimer;
function flash(message) {
  const box = $('#flash');
  box.textContent = message;
  box.hidden = false;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => (box.hidden = true), 3000);
}

function showLogin() {
  $('#dashboard').hidden = true;
  $('#top-nav').hidden = true;
  $('#login-view').hidden = false;
  $('#username').focus();
}

// every admin call goes through here, so an expired session sends you back to the login
async function adminApi(path, options) {
  try {
    return await api(path, options);
  } catch (error) {
    if (error.status === 401) showLogin();
    throw error;
  }
}

async function run(action) {
  showError('');
  try {
    await action();
  } catch (error) {
    if (error.status !== 401) showError(error.message);
  }
}

/* bookings */

function bookingRow(booking) {
  const cell = (label, ...content) => h('td', { 'data-label': label }, ...content);
  const actions = h('td', { class: 'cell-actions' });
  if (booking.status === 'active') {
    const cancelButton = h('button', { class: 'btn btn-danger btn-small', type: 'button' }, 'Cancel');
    cancelButton.onclick = () => {
      actions.replaceChildren(
        h('button', {
          class: 'btn btn-danger btn-small',
          type: 'button',
          onclick: () => run(async () => {
            await adminApi(`/api/admin/bookings/${booking.id}/cancel`, { method: 'POST' });
            flash(`Cancelled ${booking.client_name}`);
            await loadBookings();
          }),
        }, 'Yes, cancel'),
        h('button', { class: 'btn btn-quiet btn-small', type: 'button', onclick: () => actions.replaceChildren(cancelButton) }, 'Keep'),
      );
    };
    actions.append(cancelButton);
  }
  return h('tr', {},
    cell('Time', `${timeOf(booking.start_time)} - ${timeOf(booking.end_time)}`),
    cell('Client', h('span', {}, booking.client_name, h('a', { class: 'phone', href: `tel:${booking.client_phone}` }, formatPhone(booking.client_phone)))),
    cell('Service', booking.service.name),
    cell('Price', price(booking.service.price)),
    cell('Code', booking.code),
    cell('Status', h('span', { class: `badge badge-${booking.status}` }, booking.status === 'active' ? 'Active' : 'Cancelled')),
    actions,
  );
}

function renderBookings(rows) {
  const list = $('#bookings-list');
  const active = rows.filter((row) => row.status === 'active');
  const total = active.reduce((sum, row) => sum + row.service.price, 0);
  $('#day-summary').textContent = active.length
    ? `${active.length} active ${active.length === 1 ? 'booking' : 'bookings'}, ${price(total)}`
    : '';

  if (!rows.length) {
    list.replaceChildren(h('p', { class: 'empty' }, 'No bookings for this day.'));
    return;
  }
  const head = h('tr', {}, ...['Time', 'Client', 'Service', 'Price', 'Code', 'Status', ''].map((name) => h('th', {}, name)));
  list.replaceChildren(h('table', { class: 'table' }, h('thead', {}, head), h('tbody', {}, ...rows.map(bookingRow))));
}

async function loadBookings() {
  const rows = await adminApi(`/api/admin/bookings?date=${state.day}&status=${state.status}`);
  renderBookings(rows);
}

function setDay(day) {
  state.day = day;
  $('#day-input').value = day;
  run(loadBookings);
}

function moveDay(delta) {
  const date = parseDay(state.day);
  date.setDate(date.getDate() + delta);
  setDay(toDayString(date));
}

/* services */

function durationOptions(selected) {
  const options = [];
  for (let minutes = 15; minutes <= 240; minutes += 15) {
    options.push(h('option', { value: minutes, selected: minutes === selected }, minutesLabel(minutes)));
  }
  return options;
}

function serviceRow(service) {
  const status = h('span', { class: `badge ${service.is_active ? 'badge-active' : ''}` }, service.is_active ? 'Visible' : 'Hidden');

  if (state.editing === service.id) {
    const name = h('input', { type: 'text', value: service.name, maxlength: 60, 'aria-label': 'Name' });
    const duration = h('select', { 'aria-label': 'Duration' }, ...durationOptions(service.duration_minutes));
    const cost = h('input', { type: 'number', value: service.price, min: 0, step: 100, 'aria-label': 'Price' });
    return h('tr', {},
      h('td', { 'data-label': 'Name' }, name),
      h('td', { 'data-label': 'Duration' }, duration),
      h('td', { 'data-label': 'Price', class: 'num-col' }, cost),
      h('td', { 'data-label': 'Status' }, status),
      h('td', { class: 'cell-actions' },
        h('button', {
          class: 'btn btn-small',
          type: 'button',
          onclick: () => run(async () => {
            await adminApi(`/api/admin/services/${service.id}`, {
              method: 'PATCH',
              body: { name: name.value, duration_minutes: Number(duration.value), price: Number(cost.value) },
            });
            state.editing = null;
            flash('Service saved');
            await loadServices();
          }),
        }, 'Save'),
        h('button', { class: 'btn btn-quiet btn-small', type: 'button', onclick: () => { state.editing = null; renderServices(); } }, 'Cancel'),
      ),
    );
  }

  return h('tr', { class: service.is_active ? '' : 'row-hidden' },
    h('td', { 'data-label': 'Name' }, service.name),
    h('td', { 'data-label': 'Duration' }, minutesLabel(service.duration_minutes)),
    h('td', { 'data-label': 'Price', class: 'num-col' }, price(service.price)),
    h('td', { 'data-label': 'Status' }, status),
    h('td', { class: 'cell-actions' },
      h('button', { class: 'btn btn-quiet btn-small', type: 'button', onclick: () => { state.editing = service.id; renderServices(); } }, 'Edit'),
      h('button', {
        class: 'btn btn-quiet btn-small',
        type: 'button',
        onclick: () => run(async () => {
          await adminApi(`/api/admin/services/${service.id}`, { method: 'PATCH', body: { is_active: !service.is_active } });
          await loadServices();
        }),
      }, service.is_active ? 'Hide' : 'Show'),
    ),
  );
}

function renderServices() {
  const head = h('tr', {}, ...['Name', 'Duration', 'Price', 'Status', ''].map((name, i) => h('th', { class: i === 2 ? 'num-col' : '' }, name)));
  $('#services-list').replaceChildren(
    h('table', { class: 'table' }, h('thead', {}, head), h('tbody', {}, ...state.services.map(serviceRow))),
  );
}

async function loadServices() {
  state.services = await adminApi('/api/admin/services');
  renderServices();
}

async function addService(event) {
  event.preventDefault();
  await run(async () => {
    await adminApi('/api/admin/services', {
      method: 'POST',
      body: {
        name: $('#new-name').value,
        duration_minutes: Number($('#new-duration').value),
        price: Number($('#new-price').value),
      },
    });
    $('#service-form').reset();
    $('#new-duration').value = '30';
    flash('Service added');
    await loadServices();
  });
}

/* working hours */

function hoursRow(day) {
  const open = h('input', { type: 'checkbox', checked: day.is_open, id: `open-${day.weekday}` });
  const from = h('input', { type: 'time', step: 900, value: day.open_time.slice(0, 5), 'aria-label': `${DAY_NAMES[day.weekday]} opens` });
  const to = h('input', { type: 'time', step: 900, value: day.close_time.slice(0, 5), 'aria-label': `${DAY_NAMES[day.weekday]} closes` });
  const sync = () => { from.disabled = to.disabled = !open.checked; };
  open.addEventListener('change', sync);
  sync();
  const row = h('div', { class: 'hours-row', 'data-weekday': day.weekday },
    h('span', { class: 'hours-day' }, DAY_NAMES[day.weekday]),
    h('label', { class: 'open-box', for: `open-${day.weekday}` }, open, 'Open'),
    h('span', { class: 'hours-times' }, from, 'to', to),
  );
  row.read = () => ({ weekday: day.weekday, is_open: open.checked, open_time: from.value, close_time: to.value });
  return row;
}

async function loadHours() {
  const days = await adminApi('/api/admin/hours');
  $('#hours-rows').replaceChildren(...days.map(hoursRow));
}

async function saveHours(event) {
  event.preventDefault();
  await run(async () => {
    const days = [...$('#hours-rows').children].map((row) => row.read());
    await adminApi('/api/admin/hours', { method: 'PUT', body: { days } });
    flash('Working hours saved');
    await loadHours();
  });
}

/* page setup */

function openTab(button) {
  for (const tab of document.querySelectorAll('.tab')) {
    const selected = tab === button;
    tab.setAttribute('aria-selected', selected);
    $(`#${tab.dataset.panel}`).hidden = !selected;
  }
  showError('');
}

async function showDashboard() {
  $('#login-view').hidden = true;
  $('#dashboard').hidden = false;
  $('#top-nav').hidden = false;
  $('#new-duration').replaceChildren(...durationOptions(30));
  await run(async () => {
    state.shop = await api('/api/shop');
    setDay(state.shop.today);
    await Promise.all([loadServices(), loadHours()]);
  });
}

async function login(event) {
  event.preventDefault();
  const box = $('#login-error');
  box.hidden = true;
  try {
    await api('/api/admin/login', {
      method: 'POST',
      body: { username: $('#username').value, password: $('#password').value },
    });
    $('#password').value = '';
    await showDashboard();
  } catch (error) {
    box.textContent = error.message;
    box.hidden = false;
  }
}

async function start() {
  $('#login-form').addEventListener('submit', login);
  $('#logout-button').addEventListener('click', async () => {
    await api('/api/admin/logout', { method: 'POST' });
    showLogin();
  });
  for (const tab of document.querySelectorAll('.tab')) tab.addEventListener('click', () => openTab(tab));
  $('#prev-day').addEventListener('click', () => moveDay(-1));
  $('#next-day').addEventListener('click', () => moveDay(1));
  $('#today-button').addEventListener('click', () => setDay(state.shop.today));
  $('#day-input').addEventListener('change', (event) => event.target.value && setDay(event.target.value));
  for (const radio of document.querySelectorAll('input[name="status"]')) {
    radio.addEventListener('change', () => {
      state.status = radio.value;
      run(loadBookings);
    });
  }
  $('#service-form').addEventListener('submit', addService);
  $('#hours-form').addEventListener('submit', saveHours);

  try {
    await api('/api/admin/me');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return showLogin();
    $('#login-view').hidden = false;
    $('#login-error').textContent = error.message;
    $('#login-error').hidden = false;
    return;
  }
  await showDashboard();
}

start();
