export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: 'same-origin',
      headers: method === 'GET' ? { Accept: 'application/json' } : {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'donnih-web',
      },
      body: method === 'GET' ? undefined : JSON.stringify(body ?? {}),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Tidak dapat terhubung ke server. Periksa koneksi lalu coba lagi.', 0);
  }
  const data = await response.json().catch(() => null) as T & { error?: string } | null;
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('session-expired'));
    }
    throw new ApiError(data?.error || `Permintaan gagal (${response.status}). Silakan coba lagi.`, response.status);
  }
  if (data === null) throw new ApiError('Respons server tidak valid. Silakan coba lagi.', response.status);
  return data;
}

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Terjadi kesalahan. Silakan coba lagi.';
export const money = (amount: number) => new Intl.NumberFormat('id-ID', {
  style: 'currency', currency: 'IDR', maximumFractionDigits: 0,
}).format(amount);
export function dateTime(value: string) {
  // SQLite timestamps without an offset represent UTC in this API.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value.replace(' ', 'T')}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('id-ID', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export async function uploadImage(file: File, kind: 'avatar' | 'menu') {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    throw new Error('Pilih gambar berformat PNG, JPEG, atau WebP.');
  }
  if (file.size > 2 * 1024 * 1024) throw new Error('Ukuran gambar maksimal 2 MB.');
  const data_url = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Gambar tidak dapat dibaca.'));
    reader.readAsDataURL(file);
  });
  return api<{ url: string }>('/uploads', 'POST', { data_url, kind });
}
