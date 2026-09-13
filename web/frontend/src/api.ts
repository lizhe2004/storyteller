import type { StoryDetail } from './types'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: 'include', ...options })
  if (res.status === 401) { window.dispatchEvent(new CustomEvent('storyteller:logout')) }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '请求没有完成')
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  me: () => request<{ authenticated: boolean }>('/api/me'),
  login: (password: string) => request<void>('/api/auth', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ password }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  options: () => request<{ lengths: string[]; complexities: string[]; tts_providers: {name: string}[]; sound_enabled: boolean }>('/api/config/options'),
  stories: () => request<{ stories: { id: string; dir_name: string; title: string; state: string; created_at: string }[] }>('/api/stories'),
  story: (ref: string) => request<StoryDetail>('/api/stories/' + encodeURIComponent(ref)),
}
