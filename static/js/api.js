export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// FastAPI sends a string for most errors and a list for validation errors
function messageFrom(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail[0].msg.replace(/^Value error, /, '');
  return 'Something went wrong. Please try again.';
}

export async function api(path, { method = 'GET', body } = {}) {
  const init = { method, headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection.');
  }
  if (response.status === 204) return null;

  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, messageFrom(data && data.detail));
  return data;
}
