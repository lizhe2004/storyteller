import type { ConnectionTestPayload, ConnectionTestResult, ModelOption, SettingsMutationResponse, SettingsPatch, SettingsResponse, StoryDetail, VoiceAnalysisJob, VoiceClipResponse, VoiceListResponse } from './types'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: 'include', ...options })
  if (res.status === 401) { window.dispatchEvent(new CustomEvent('storyteller:logout')) }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '请求没有完成')
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  authStatus: () => request<{ setup_required: boolean; setup_available: boolean }>('/api/auth/status'),
  me: () => request<{ authenticated: boolean }>('/api/me'),
  login: (password: string) => request<void>('/api/auth', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ password }) }),
  setup: (code: string, password: string) => request<void>('/api/auth/setup', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ code, password }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  options: () => request<{ lengths: string[]; complexities: string[]; tts_providers: {name: string}[]; sound_enabled: boolean; llm_models: ModelOption[]; audio_models: ModelOption[] }>('/api/config/options'),
  stories: () => request<{ stories: { id: string; dir_name: string; title: string; state: string; created_at: string }[] }>('/api/stories'),
  story: (ref: string) => request<StoryDetail>('/api/stories/' + encodeURIComponent(ref)),
  voiceAnalysisJobs: () => request<{jobs: VoiceAnalysisJob[]}>('/api/voice-analysis/jobs'),
  voiceAnalysisJob: (id: string) => request<VoiceAnalysisJob>('/api/voice-analysis/jobs/' + encodeURIComponent(id)),
  createVoiceAnalysisJob: (options: object = {}) => request<VoiceAnalysisJob>('/api/voice-analysis/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(options)}),
  resumeVoiceAnalysisJob: (id: string) => request<VoiceAnalysisJob>('/api/voice-analysis/jobs/' + encodeURIComponent(id) + '/resume', {method:'POST'}),
  cancelVoiceAnalysisJob: (id: string) => request<VoiceAnalysisJob>('/api/voice-analysis/jobs/' + encodeURIComponent(id) + '/cancel', {method:'POST'}),
  approveVoiceAnalysisSuggestion: (jobId: string, suggestionId: string) => request<any>('/api/voice-analysis/jobs/' + encodeURIComponent(jobId) + '/suggestions/' + encodeURIComponent(suggestionId) + '/approve', {method:'POST'}),
  rejectVoiceAnalysisSuggestion: (jobId: string, suggestionId: string) => request<any>('/api/voice-analysis/jobs/' + encodeURIComponent(jobId) + '/suggestions/' + encodeURIComponent(suggestionId) + '/reject', {method:'POST'}),
  getSettings: () => request<SettingsResponse>('/api/settings'),
  patchSettings: (patch: SettingsPatch) => request<SettingsMutationResponse>('/api/settings', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(patch)}),
  testSettings: (kind: 'llm' | 'tts', payload: ConnectionTestPayload) => request<ConnectionTestResult>('/api/settings/test/' + kind, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}),
  fetchModels: (kind: 'llm' | 'tts', payload: ConnectionTestPayload) => request<{ok: boolean; provider: string; models: {id: string; retiring?: boolean}[]}>('/api/settings/models/' + kind, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}),
  resetSettings: (paths: string[]) => request<SettingsMutationResponse>('/api/settings/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({paths})}),
  voices: (filters: { provider?: string; model?: string; gender?: string; age?: string; page?: number; page_size?: number } = {}) => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)) })
    return request<VoiceListResponse>('/api/voices?' + params.toString())
  },
  updateVoiceAge: (key: string, age: string[]) => request<any>('/api/voices/' + encodeURIComponent(key), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({age})}),
  voiceClips: (key: string) => request<VoiceClipResponse>('/api/voices/' + encodeURIComponent(key) + '/clips'),
}
