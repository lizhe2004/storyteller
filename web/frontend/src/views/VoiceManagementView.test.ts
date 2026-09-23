import { createApp, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import VoiceManagementView from './VoiceManagementView.vue'
import router from '../router'

const mounted: { app: App; element: HTMLElement }[] = []
const response = { page: 1, page_size: 50, total: 1, voices: [{ key: 'mock|model-a|v1', provider: 'mock', model: 'model-a', voice_id: 'v1', name: '温柔女声', gender: 'female', age: ['young_adult'], category: '有声阅读', description: '温柔', clip_count: 1, has_clips: true }] }

beforeEach(() => vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => response }))))
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
})
