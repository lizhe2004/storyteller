import { createApp, nextTick, type App } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { SettingsMutationResponse, SettingsResponse } from '../types'
import SettingsView from './SettingsView.vue'

const fullSecret = 'full-secret-must-never-render'

const settings: SettingsResponse = {
  web: {
    passwords: { configured: true, count: 2, masked: '********' },
    secret: { configured: true, masked: '********cret', value: fullSecret },
    token_ttl_days: 30,
    host: '127.0.0.1',
    port: 8000,
    concurrency: 2,
    rate_limit_per_min: 10,
    filler_voice: 'narrator',
  },
  llm: {
    providers: ['mock'],
    default_provider: 'mock',
    provider_config: {
      mock: { type: 'mock', api_key: { configured: true, masked: '********-key', value: fullSecret }, model: 'story-model' },
    },
  },
  tts: {
    providers: ['mock-tts'],
    default_provider: 'mock-tts',
    provider_config: {
      'mock-tts': { type: 'mock', api_key: { configured: true, masked: '********-tts' }, model: 'voice-model', resource_id: 'workspace-a' },
    },
  },
  sound: {
    enabled: true,
    dir: '/data/sounds',
    providers: ['mock-sound'],
    default_provider: 'mock-sound',
    provider_config: {
      'mock-sound': { type: 'mock', api_key: { configured: false, masked: null }, model: 'foley-model' },
    },
  },
  sources: {
    web: { passwords: 'environment', secret: 'environment', token_ttl_days: 'default', host: 'environment', port: 'default', concurrency: 'admin', rate_limit_per_min: 'default', filler_voice: 'admin' },
    llm: { providers: 'environment', default_provider: 'admin', provider_config: { mock: { type: 'default', api_key: 'environment', model: 'admin' } } },
    tts: { providers: 'admin', default_provider: 'admin', provider_config: { 'mock-tts': { type: 'default', api_key: 'environment', model: 'admin', resource_id: 'environment' } } },
    sound: { enabled: 'default', dir: 'environment', providers: 'admin', default_provider: 'admin', provider_config: { 'mock-sound': { type: 'default', api_key: 'default', model: 'admin' } } },
  },
  config_error: null,
}

const mutationResponse = (): SettingsMutationResponse => ({
  version: 'version-1',
  updated_at: '2026-09-14T08:00:00Z',
  effective_for: 'new_jobs',
  message: '保存成功；配置对新任务生效，运行中任务不受影响',
  settings,
})

interface MountedView {
  app: App
  element: HTMLElement
  router: Router
}

const mounted: MountedView[] = []

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

async function mountSettings(): Promise<MountedView> {
  vi.spyOn(api, 'getSettings').mockResolvedValue(structuredClone(settings))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings', component: SettingsView },
      { path: '/elsewhere', component: { template: '<p>elsewhere</p>' } },
    ],
  })
  await router.push('/settings')
  await router.isReady()
  const element = document.createElement('div')
  document.body.appendChild(element)
  const app = createApp({ template: '<router-view />' }).use(router)
  app.mount(element)
  const result = { app, element, router }
  mounted.push(result)
  await settle()
  return result
}

function input(element: HTMLElement, testId: string, value: string) {
  const control = element.querySelector(`[data-testid="${testId}"]`) as HTMLInputElement
  control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
}

function click(element: HTMLElement, testId: string) {
  const control = element.querySelector(`[data-testid="${testId}"]`) as HTMLButtonElement
  control.click()
}

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
  vi.restoreAllMocks()
})

describe('SettingsView', () => {
  it('renders four collapsible groups with configuration source labels', async () => {
    const { element } = await mountSettings()

    expect(element.textContent).toContain('Web 服务')
    expect(element.textContent).toContain('大模型')
    expect(element.textContent).toContain('TTS 音色服务')
    expect(element.textContent).toContain('音效与高级设置')
    expect(element.textContent).toContain('后台设置')
    expect(element.textContent).toContain('环境变量')
    expect(element.textContent).toContain('程序默认值')
    expect(element.querySelectorAll('details.settings-section')).toHaveLength(4)
  })

  it('shows only masked secret status and leaves replacement fields empty', async () => {
    const { element } = await mountSettings()

    expect(element.textContent).toContain('********cret')
    expect(element.textContent).toContain('********-key')
    expect(element.textContent).not.toContain(fullSecret)
    const secretInputs = Array.from(element.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    expect(secretInputs.length).toBeGreaterThanOrEqual(3)
    expect(secretInputs.every(control => control.value === '')).toBe(true)
  })

  it('saves only the edited group and shows that changes apply to new jobs', async () => {
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()

    input(element, 'web-concurrency', '4')
    click(element, 'save-web')
    await settle()

    expect(patchSettings).toHaveBeenCalledTimes(1)
    expect(patchSettings.mock.calls[0][0]).toMatchObject({ web: { concurrency: 4 } })
    expect(patchSettings.mock.calls[0][0]).not.toHaveProperty('llm')
    expect(element.textContent).toContain('已对新任务生效')
  })

  it('serializes the provider list as an array when edited as text', async () => {
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()

    input(element, 'llm-providers', 'mock,gemini')
    click(element, 'save-llm')
    await settle()

    expect(patchSettings.mock.calls[0][0]).toMatchObject({ llm: { providers: ['mock', 'gemini'] } })
  })

  it('shows successful and failed connection test results without saving', async () => {
    const testSettings = vi.spyOn(api, 'testSettings')
      .mockResolvedValueOnce({ ok: true, provider: 'mock', message: '连接成功' })
      .mockRejectedValueOnce(new Error('连接测试失败，请检查供应商配置和网络连接'))
    const patchSettings = vi.spyOn(api, 'patchSettings')
    const { element } = await mountSettings()

    click(element, 'test-llm')
    await settle()
    expect(element.querySelector('[data-testid="status-llm"]')?.textContent).toContain('连接成功')

    click(element, 'test-tts')
    await settle()
    expect(element.querySelector('[data-testid="status-tts"]')?.textContent).toContain('连接测试失败')
    expect(testSettings).toHaveBeenNthCalledWith(1, 'llm', expect.objectContaining({ provider: 'mock' }))
    expect(testSettings).toHaveBeenNthCalledWith(2, 'tts', expect.objectContaining({ provider: 'mock-tts' }))
    expect(patchSettings).not.toHaveBeenCalled()
  })

  it('resets a group only after confirmation', async () => {
    const resetSettings = vi.spyOn(api, 'resetSettings').mockResolvedValue(mutationResponse())
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { element } = await mountSettings()

    click(element, 'reset-web')
    await settle()

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(resetSettings).toHaveBeenCalledTimes(1)
    expect(resetSettings.mock.calls[0][0]).toEqual(expect.arrayContaining(['web.secret', 'web.concurrency', 'web.rate_limit_per_min']))
  })

  it('warns before route navigation when there are unsaved changes', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { element, router } = await mountSettings()

    input(element, 'web-concurrency', '5')
    await router.push('/elsewhere')

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/settings')
  })
})
