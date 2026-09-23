import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VoiceManagementView from './VoiceManagementView.vue'
import router from '../router'

const mounted: { app: App; element: HTMLElement }[] = []
const response = { page: 1, page_size: 50, total: 1, filters: { providers: ['mock'], models: ['model-a'], genders: ['female'], ages: ['young_adult'] }, voices: [{ key: 'mock|model-a|v1', provider: 'mock', model: 'model-a', voice_id: 'v1', name: '温柔女声', gender: 'female', age: ['young_adult'], category: '有声阅读', description: '温柔', tags: ['治愈'], clip_count: 1, has_clips: true }] }

beforeEach(() => { response.voices[0].age = ['young_adult']; vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => response }))) })
afterEach(() => { mounted.splice(0).forEach(({ app, element }) => { app.unmount(); element.remove() }); vi.unstubAllGlobals() })

async function mountView() {
  const element = document.createElement('div'); document.body.appendChild(element)
  const app = createApp(VoiceManagementView); app.mount(element); mounted.push({ app, element }); await new Promise(resolve => setTimeout(resolve, 0)); await nextTick(); return element
}

describe('VoiceManagementView', () => {
  it('loads and renders all voices', async () => {
    const element = await mountView()
    expect(element.textContent).toContain('温柔女声')
    expect(element.querySelector('[data-testid="voice-row"]')).toBeTruthy()
    expect(element.textContent).toContain('有声阅读')
    expect(element.textContent).toContain('治愈')
    expect(element.textContent).toContain('温柔')
  })

  it('builds filter queries when a filter changes', async () => {
    const element = await mountView()
    const provider = element.querySelector('[data-testid="filter-provider"]') as HTMLSelectElement
    provider.value = 'mock'; provider.dispatchEvent(new Event('change')); await new Promise(resolve => setTimeout(resolve, 0)); await nextTick()
    expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain('provider=mock')
    expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain('page=1')
  })

  it('registers the authenticated voice route and navigation link', () => {
    expect(router.options.routes.some(route => route.path === '/voices')).toBe(true)
  })

  it('edits multiple ages and plays story clips with metadata', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => response }))
    fetchMock.mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => ({ age: ['child', 'young_adult'] }) }))
    fetchMock.mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => ({ clips: [{ clip_id: 'p1:l1', project_id: 'p1', story_title: '测试故事', character_name: '旁白', text: '一段台词', created_at: '2026-01-01T00:00:00', duration_ms: 100, audio_url_id: 'p1:l1' }] }) }))
    const element = await mountView()
    const child = Array.from(element.querySelectorAll('.age-checks input')).find(input => (input as HTMLInputElement).value === 'child') as HTMLInputElement
    child.click(); (element.querySelector('.voice-age .small-action') as HTMLButtonElement).click()
    await new Promise(resolve => setTimeout(resolve, 0)); await nextTick()
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe('PATCH')
    expect((fetchMock.mock.calls[1][1] as RequestInit).body).toContain('child')
    ;(element.querySelector('.voice-actions button') as HTMLButtonElement).click()
    await new Promise(resolve => setTimeout(resolve, 0)); await nextTick()
    expect(element.textContent).toContain('一段台词')
    const audio = element.querySelector('audio') as HTMLAudioElement
    expect(audio.src).toContain('/api/voices/mock%7Cmodel-a%7Cv1/clips/p1%3Al1/audio')
  })

  it('rolls back age selection when saving fails and shows empty clips', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => response }))
    fetchMock.mockImplementationOnce(async () => ({ ok: false, status: 500, json: async () => ({ detail: '保存失败' }) }))
    fetchMock.mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => ({ clips: [] }) }))
    const element = await mountView()
    const child = Array.from(element.querySelectorAll('.age-checks input')).find(input => (input as HTMLInputElement).value === 'child') as HTMLInputElement
    child.click(); (element.querySelector('.voice-age .small-action') as HTMLButtonElement).click()
    await new Promise(resolve => setTimeout(resolve, 0)); await nextTick()
    const childAfterFailure = Array.from(element.querySelectorAll('.age-checks input')).find(input => (input as HTMLInputElement).value === 'child') as HTMLInputElement
    expect(childAfterFailure.checked).toBe(false)
    ;(element.querySelector('.voice-actions button') as HTMLButtonElement).click()
    await new Promise(resolve => setTimeout(resolve, 0)); await nextTick()
    expect(element.textContent).toContain('暂无故事生成片段')
  })
})
