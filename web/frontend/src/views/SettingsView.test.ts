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
    providers: ['writer'],
    default_provider: 'writer',
    provider_config: {
      writer: { type: 'openai_compatible', api_key: { configured: true, masked: '********-writer' }, model: 'writer-model', base_url: 'https://llm.example/v1' },
    },
  },
  tts: {
    providers: ['mock-tts', 'aliyun'],
    default_provider: 'mock-tts',
    provider_config: {
      'mock-tts': { type: 'mock', api_key: { configured: true, masked: '********-tts' }, model: 'voice-model', resource_id: 'workspace-a' },
      aliyun: { api_key: { configured: true, masked: '********-ali' }, models: 'qwen-audio-3.0-tts-plus', workspace_id: 'workspace-a' },
      // Configured but intentionally NOT enabled: exercises the independence
      // of provider configuration from the enabled-provider set.
      volcengine: { api_key: { configured: true, masked: '********-volc' }, resource_id: 'volc-resource' },
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
    llm: { providers: 'environment', default_provider: 'admin', provider_config: { mock: { type: 'default', api_key: 'environment', model: 'admin' }, writer: { type: 'admin', api_key: 'environment', model: 'admin', base_url: 'admin' } } },
    tts: { providers: 'admin', default_provider: 'admin', provider_config: { 'mock-tts': { type: 'default', api_key: 'environment', model: 'admin', resource_id: 'environment' }, aliyun: { api_key: 'environment', models: 'admin', workspace_id: 'environment' }, volcengine: { api_key: 'environment', resource_id: 'environment' } } },
    sound: { enabled: 'default', dir: 'environment', providers: 'admin', default_provider: 'admin', provider_config: { 'mock-sound': { type: 'default', api_key: 'default', model: 'admin' } } },
  },
  config_error: null,
  provider_schemas: {
    llm: {
      types: {
        volcengine: { label: '火山引擎方舟', fields: ['api_key', 'model', 'models'] },
        openai_compatible: { label: 'OpenAI 兼容服务', fields: ['api_key', 'model', 'models', 'base_url'] },
        mock: { label: '模拟服务', fields: [] },
      },
      providers: { mock: 'mock', writer: 'openai_compatible' },
      custom_types: ['openai_compatible', 'mock'], fixed_names: ['volcengine'],
    },
    tts: {
      types: {
        aliyun: { label: '阿里云百炼', fields: ['api_key', 'models', 'workspace_id'] },
        volcengine: { label: '火山引擎语音', fields: ['api_key', 'resource_id'] },
        openai_compatible: { label: 'OpenAI 兼容服务', fields: ['api_key', 'model', 'base_url'] },
        mock: { label: '模拟服务', fields: [] },
      },
      providers: { 'mock-tts': 'mock', aliyun: 'aliyun' },
      custom_types: ['openai_compatible', 'mock'], fixed_names: ['aliyun', 'volcengine'],
    },
    sound: {
      types: { volcengine: { label: '火山引擎音效', fields: ['api_key', 'model'] }, mock: { label: '模拟服务', fields: [] } },
      providers: { 'mock-sound': 'mock' }, custom_types: ['mock'], fixed_names: ['volcengine'],
    },
  },
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

async function mountSettings(settingsResponse: SettingsResponse = settings): Promise<MountedView> {
  vi.spyOn(api, 'getSettings').mockResolvedValue(structuredClone(settingsResponse))
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
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

function choose(element: HTMLElement, testId: string, value: string) {
  const control = element.querySelector(`[data-testid="${testId}"]`) as HTMLSelectElement
  control.value = value
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

function click(element: HTMLElement, testId: string) {
  const control = element.querySelector(`[data-testid="${testId}"]`) as HTMLButtonElement
  control.click()
}

async function selectGroup(element: HTMLElement, group: string) {
  click(element, `settings-nav-${group}`)
  await settle()
}

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
  vi.restoreAllMocks()
})

describe('SettingsView', () => {
  it('renders a configuration workspace with group navigation and source labels', async () => {
    const { element } = await mountSettings()

    expect(element.textContent).toContain('Web 服务')
    expect(element.textContent).toContain('大模型')
    expect(element.textContent).toContain('TTS 音色服务')
    expect(element.textContent).toContain('音效服务')
    expect(element.textContent).toContain('后台设置')
    expect(element.textContent).toContain('环境变量')
    expect(element.textContent).toContain('程序默认值')
    expect(element.querySelector('[data-testid="settings-navigation"]')).not.toBeNull()
    expect(element.querySelector('[data-testid="settings-navigation"] [aria-current="page"]')?.textContent).toContain('Web 服务')
    expect(element.querySelectorAll('[data-testid="settings-group-panel"]')).toHaveLength(1)
    expect(element.querySelector('[data-testid="settings-group-panel"]')?.textContent).toContain('登录密码')
  })

  it('switches configuration groups without showing multiple forms at once', async () => {
    const { element } = await mountSettings()

    const llmLink = element.querySelector('[data-testid="settings-nav-llm"]') as HTMLButtonElement
    llmLink.click()
    await settle()

    expect(llmLink.getAttribute('aria-current')).toBe('page')
    expect(element.querySelectorAll('[data-testid="settings-group-panel"]')).toHaveLength(1)
    expect(element.querySelector('[data-testid="settings-group-panel"]')?.textContent).toContain('服务类型')
    expect(element.querySelector('[data-testid="settings-group-panel"]')?.textContent).not.toContain('登录密码')
  })

  it('renders only fields declared for the active provider implementation', async () => {
    const { element } = await mountSettings()

    await selectGroup(element, 'llm')
    const llmCards = Array.from(element.querySelectorAll('.provider-card')) as HTMLElement[]
    const writerCard = llmCards.find(card => card.querySelector('h4')?.textContent === 'writer')!
    expect(writerCard.textContent).toContain('Base URL')
    expect(writerCard.textContent).not.toContain('Endpoint')
    expect(writerCard.textContent).not.toContain('资源 ID')

    await selectGroup(element, 'tts')
    const ttsCards = Array.from(element.querySelectorAll('.provider-card')) as HTMLElement[]
    const aliyunCard = ttsCards.find(card => card.querySelector('h4')?.textContent === 'aliyun')!
    const mockTtsCard = ttsCards.find(card => card.querySelector('h4')?.textContent === 'mock-tts')!
    expect(aliyunCard.textContent).toContain('模型白名单')
    expect(aliyunCard.textContent).toContain('Workspace ID')
    expect(aliyunCard.textContent).not.toContain('Endpoint')
    expect(aliyunCard.textContent).not.toContain('资源 ID')
    expect(mockTtsCard.textContent).not.toContain('API Key')
    expect(mockTtsCard.textContent).not.toContain('模型白名单')
  })

  it('shows one LLM provider without a default provider control or standalone model field', async () => {
    const { element } = await mountSettings()
    await selectGroup(element, 'llm')

    expect(element.querySelector('[data-testid="llm-providers"]')).toBeNull()
    expect(element.querySelector('[data-testid="llm-default-provider"]')).toBeNull()
    expect(element.querySelectorAll('[data-testid="llm-provider-type"]')).toHaveLength(1)
    // The standalone model input is gone; the default is managed inside
    // the candidate-list editor instead.
    expect(element.querySelectorAll('[data-testid^="field-llm-"][data-testid$="-model"]')).toHaveLength(0)
    expect(element.querySelector('[data-testid="candidate-list-llm-writer"]')).not.toBeNull()
  })

  it('removes the unused TTS default and limits Sound settings to one provider', async () => {
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')
    expect(element.querySelector('[data-testid="tts-default-provider"]')).toBeNull()

    await selectGroup(element, 'sound')
    expect(element.querySelector('[data-testid="sound-providers"]')).toBeNull()
    expect(element.querySelectorAll('[data-testid="sound-provider-type"]')).toHaveLength(1)
  })

  it('renders and preserves custom TTS providers that use the backend Volcengine fallback', async () => {
    const customSettings = structuredClone(settings)
    customSettings.tts.providers = ['custom-voice']
    customSettings.tts.provider_config = {
      'custom-voice': { api_key: { configured: true, masked: '********-voice' }, resource_id: 'custom-resource' },
    }
    customSettings.provider_schemas.tts.providers = { 'custom-voice': 'volcengine' }
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings(customSettings)
    await selectGroup(element, 'tts')

    const card = element.querySelector('[data-testid="provider-card-tts-custom-voice"]') as HTMLElement
    expect(card.textContent).toContain('资源 ID')
    expect(card.textContent).toContain('********-voice')
    click(element, 'save-tts')
    await settle()

    expect(patchSettings.mock.calls[0][0]).toMatchObject({
      tts: { providers: ['custom-voice'], provider_config: { 'custom-voice': { type: 'volcengine', resource_id: 'custom-resource' } } },
    })
  })

  it('clears a legacy TTS default when saving its provider pool', async () => {
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')
    click(element, 'save-tts')
    await settle()

    expect(patchSettings.mock.calls[0][0]).toMatchObject({ tts: { default_provider: null } })
  })

  it('keeps unsaved state per group when another group is saved', async () => {
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()

    input(element, 'web-concurrency', '4')
    await selectGroup(element, 'llm')
    input(element, 'field-llm-writer-base_url', 'https://llm.example/v2')
    click(element, 'save-llm')
    await settle()

    expect(patchSettings).toHaveBeenCalledTimes(1)
    expect(element.querySelector('[data-testid="settings-nav-web"]')?.textContent).toContain('未保存')
    expect(element.querySelector('[data-testid="settings-nav-llm"]')?.textContent).not.toContain('未保存')
    await selectGroup(element, 'web')
    expect((element.querySelector('[data-testid="web-concurrency"]') as HTMLInputElement).value).toBe('4')
    expect(element.querySelector('.settings-unsaved')?.textContent).toContain('有未保存的修改')
  })

  it('shows only masked secret status and leaves replacement fields empty', async () => {
    const { element } = await mountSettings()

    expect(element.textContent).toContain('********cret')
    expect(element.textContent).not.toContain(fullSecret)
    const webSecretInputs = Array.from(element.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    expect(webSecretInputs.every(control => control.value === '')).toBe(true)

    await selectGroup(element, 'llm')
    expect(element.textContent).toContain('********-writer')
    await selectGroup(element, 'tts')
    expect(element.textContent).toContain('********-ali')
    expect(element.textContent).not.toContain(fullSecret)
    const secretInputs = Array.from(element.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    // aliyun + volcengine (configured but disabled) both render key fields.
    expect(secretInputs).toHaveLength(2)
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

  it('serializes exactly one selected LLM provider and clears the unused default', async () => {
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()

    await selectGroup(element, 'llm')
    choose(element, 'llm-provider-type', 'openai_compatible')
    await settle()
    // The default model is set through the candidate editor: add a custom
    // model from the search box, then mark it as default.
    input(element, 'candidate-filter-llm-openai', 'gemini-pro')
    await settle()
    click(element, 'candidate-add-llm-openai')
    await settle()
    click(element, 'candidate-default-llm-openai-gemini-pro')
    await settle()
    input(element, 'llm-openai-api-key', 'new-key')
    input(element, 'field-llm-openai-base_url', 'https://llm.example/v1')
    click(element, 'save-llm')
    await settle()

    expect(patchSettings.mock.calls[0][0]).toMatchObject({
      llm: {
        providers: ['openai'],
        default_provider: null,
        provider_config: { openai: { type: 'openai_compatible', model: 'gemini-pro', models: 'gemini-pro', api_key: 'new-key', base_url: 'https://llm.example/v1' } },
      },
    })
  })

  it('shows successful and failed connection test results without saving', async () => {
    const testSettings = vi.spyOn(api, 'testSettings')
      .mockResolvedValueOnce({ ok: true, provider: 'mock', message: '连接成功' })
      .mockRejectedValueOnce(new Error('连接测试失败，请检查供应商配置和网络连接'))
    const patchSettings = vi.spyOn(api, 'patchSettings')
    const { element } = await mountSettings()

    await selectGroup(element, 'llm')
    click(element, 'test-llm')
    await settle()
    expect(element.querySelector('[data-testid="status-llm"]')?.textContent).toContain('连接成功')

    await selectGroup(element, 'tts')
    // Narrow the enabled providers down to aliyun via the picker.
    click(element, 'tts-provider-picker-toggle')
    await settle()
    click(element, 'tts-provider-option-mock-tts')
    await settle()
    click(element, 'test-tts')
    await settle()
    expect(element.querySelector('[data-testid="status-tts"]')?.textContent).toContain('连接测试失败')
    expect(testSettings).toHaveBeenNthCalledWith(1, 'llm', expect.objectContaining({ provider: 'writer' }))
    expect(testSettings).toHaveBeenNthCalledWith(2, 'tts', expect.objectContaining({ provider: 'aliyun' }))
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

  it('auto-fetches TTS models into the whitelist editor', async () => {
    const fetchModels = vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'aliyun', models: [{ id: 'qwen-audio-3.0-tts-plus' }, { id: 'qwen-audio-new' }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')

    // Mock providers have no model editor; aliyun fetched automatically.
    expect(element.querySelector('[data-testid="candidate-list-tts-mock-tts"]')).toBeNull()
    expect(fetchModels).toHaveBeenCalledWith('tts', expect.objectContaining({ provider: 'aliyun' }))

    const existingBox = element.querySelector('[data-testid="candidate-check-tts-aliyun-qwen-audio-3.0-tts-plus"]') as HTMLInputElement
    const newBox = element.querySelector('[data-testid="candidate-check-tts-aliyun-qwen-audio-new"]') as HTMLInputElement
    expect(existingBox.checked).toBe(true)
    expect(newBox.checked).toBe(false)

    newBox.click()
    await settle()
    expect(newBox.checked).toBe(true)
    expect(element.querySelector('[data-testid="settings-nav-tts"]')?.textContent).toContain('未保存')
  })

  it('keeps LLM and TTS model pools separate for same-named providers', async () => {
    const isolated = structuredClone(settings)
    isolated.llm.providers = ['aliyun']
    isolated.llm.default_provider = 'aliyun'
    ;(isolated.llm.provider_config as any) = { aliyun: { type: 'openai_compatible', api_key: { configured: true, masked: '********-k' }, model: 'llm-default' } }
    ;(isolated.provider_schemas.llm.providers as any) = { aliyun: 'openai_compatible' }
    const fetchModels = vi.spyOn(api, 'fetchModels').mockImplementation(async (kind) => ({
      ok: true,
      provider: 'aliyun',
      models: [{ id: kind === 'llm' ? 'llm-only-model' : 'tts-only-model' }],
    }))
    const { element } = await mountSettings(isolated)

    await selectGroup(element, 'llm')
    expect(element.querySelector('[data-testid="candidate-list-llm-aliyun"]')?.textContent).toContain('llm-only-model')

    await selectGroup(element, 'tts')
    const ttsList = element.querySelector('[data-testid="candidate-list-tts-aliyun"]') as HTMLElement
    expect(ttsList.textContent).toContain('tts-only-model')
    expect(ttsList.textContent).not.toContain('llm-only-model')
    // llm:aliyun + tts:aliyun + tts:volcengine (configured, has an editor).
    expect(fetchModels).toHaveBeenCalledTimes(3)
  })

  it('marks retiring models with a badge', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'writer', models: [{ id: 'writer-model' }, { id: 'writer-old', retiring: true }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'llm')

    const list = element.querySelector('[data-testid="candidate-list-llm-writer"]') as HTMLElement
    const rows = Array.from(list.querySelectorAll('li'))
    const retiringRow = rows.find(row => row.textContent?.includes('writer-old'))
    expect(retiringRow?.textContent).toContain('即将下线')
    const activeRow = rows.find(row => row.textContent?.includes('writer-model'))
    expect(activeRow?.textContent).not.toContain('即将下线')
  })

  it('toggles TTS providers from the multi-select picker', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'volcengine', models: [{ id: 'seed-tts-2.0' }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')

    // A configured-but-disabled provider still renders its card; the badge
    // tracks enablement independently of configuration.
    const state = () => element.querySelector('[data-testid="provider-card-state-tts-volcengine"]')?.textContent
    expect(element.querySelector('[data-testid="provider-card-tts-volcengine"]')).not.toBeNull()
    expect(state()).toContain('未启用')

    click(element, 'tts-provider-picker-toggle')
    await settle()
    click(element, 'tts-provider-option-volcengine')
    await settle()
    expect(state()).toContain('已启用')
    // A freshly enabled fixed provider must resolve its type and render
    // its fields even without a schema.providers entry.
    expect(element.querySelector('[data-testid="tts-volcengine-api-key"]')).not.toBeNull()
    expect(element.querySelector('[data-testid="candidate-select-tts-volcengine-seed-tts-2.0"]')).not.toBeNull()

    // Unchecking an enabled provider keeps its configuration card.
    click(element, 'tts-provider-option-aliyun')
    await settle()
    expect(element.querySelector('[data-testid="provider-card-tts-aliyun"]')).not.toBeNull()
    expect(element.querySelector('[data-testid="provider-card-state-tts-aliyun"]')?.textContent).toContain('未启用')
  })

  it('saves configuration for a TTS provider that stays disabled', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'volcengine', models: [] })
    const patchSettings = vi.spyOn(api, 'patchSettings').mockResolvedValue(mutationResponse())
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')

    // volcengine is configured in the fixture but not enabled; editing its
    // card and saving must not add it to the enabled set.
    input(element, 'tts-volcengine-api-key', 'new-volc-key')
    input(element, 'candidate-filter-tts-volcengine', 'res-new')
    await settle()
    click(element, 'candidate-add-tts-volcengine')
    await settle()
    click(element, 'save-tts')
    await settle()

    const payload = patchSettings.mock.calls[0][0] as any
    expect(payload.tts.providers).toEqual(['mock-tts', 'aliyun'])
    expect(payload.tts.provider_config.volcengine).toMatchObject({ api_key: 'new-volc-key', resource_id: 'res-new' })
    expect(payload.tts.provider_config.aliyun).toBeDefined()
  })

  it('collapses and expands a provider card from its header', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'aliyun', models: [] })
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')

    const card = element.querySelector('[data-testid="provider-card-tts-aliyun"]') as HTMLElement
    expect(card.classList.contains('collapsed')).toBe(false)
    click(element, 'provider-card-toggle-tts-aliyun')
    await settle()
    expect(card.classList.contains('collapsed')).toBe(true)
    click(element, 'provider-card-toggle-tts-aliyun')
    await settle()
    expect(card.classList.contains('collapsed')).toBe(false)
  })

  it('auto-fetches models into checkboxes and switches the default', async () => {
    const fetchModels = vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'writer', models: [{ id: 'writer-model' }, { id: 'writer-model-2' }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'llm')

    expect(fetchModels).toHaveBeenCalledWith('llm', expect.objectContaining({ provider: 'writer' }))
    expect(element.querySelector('[data-testid="fetch-models-status-llm-writer"]')?.textContent).toContain('已拉取 2 个模型')
    const list = element.querySelector('[data-testid="candidate-list-llm-writer"]') as HTMLElement
    expect(list.textContent).toContain('writer-model')
    expect(list.textContent).toContain('writer-model-2')

    // The default row: checked + disabled checkbox, badge, no action button.
    const defaultBox = element.querySelector('[data-testid="candidate-check-llm-writer-writer-model"]') as HTMLInputElement
    expect(defaultBox.checked).toBe(true)
    expect(defaultBox.disabled).toBe(true)
    expect(element.querySelector('[data-testid="candidate-default-llm-writer-writer-model"]')).toBeNull()
    const otherBox = element.querySelector('[data-testid="candidate-check-llm-writer-writer-model-2"]') as HTMLInputElement
    expect(otherBox.checked).toBe(false)

    otherBox.click()
    await settle()
    click(element, 'candidate-default-llm-writer-writer-model-2')
    await settle()

    expect(element.querySelector('[data-testid="candidate-current-llm-writer"]')?.textContent).toContain('writer-model-2')
    // The old default stays visible but becomes an unchecked candidate row.
    expect(defaultBox.checked).toBe(false)
    expect(defaultBox.disabled).toBe(false)
    expect(element.querySelector('[data-testid="candidate-default-llm-writer-writer-model"]')).not.toBeNull()
  })

  it('adds a custom model from the search box', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'writer', models: [{ id: 'writer-model' }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'llm')

    input(element, 'candidate-filter-llm-writer', 'ep-custom-endpoint')
    await settle()
    click(element, 'candidate-add-llm-writer')
    await settle()

    const customBox = element.querySelector('[data-testid="candidate-check-llm-writer-ep-custom-endpoint"]') as HTMLInputElement
    expect(customBox).not.toBeNull()
    expect(customBox.checked).toBe(true)
    // Once added, the exact keyword no longer offers the add row.
    expect(element.querySelector('[data-testid="candidate-add-llm-writer"]')).toBeNull()

    input(element, 'candidate-filter-llm-writer', '')
    await settle()
    expect(element.querySelector('[data-testid="candidate-list-llm-writer"]')?.textContent).toContain('ep-custom-endpoint')
  })

  it('filters the candidate pool by keyword', async () => {
    vi.spyOn(api, 'fetchModels').mockResolvedValue({ ok: true, provider: 'writer', models: [{ id: 'writer-model' }, { id: 'writer-model-2' }] })
    const { element } = await mountSettings()
    await selectGroup(element, 'llm')

    input(element, 'candidate-filter-llm-writer', 'model-2')
    await settle()
    const list = element.querySelector('[data-testid="candidate-list-llm-writer"]') as HTMLElement
    const rows = Array.from(list.querySelectorAll('li')).filter(li => li.querySelector('.candidate-check'))
    expect(rows).toHaveLength(1)
    expect(rows[0].textContent).toContain('writer-model-2')
    // A non-matching keyword doubles as a custom-model offer.
    expect(list.textContent).toContain('添加“model-2”')
  })

  it('surfaces model fetch failures and keeps configured models visible', async () => {
    vi.spyOn(api, 'fetchModels').mockRejectedValue(new Error('拉取模型列表失败，请检查供应商配置和网络连接'))
    const { element } = await mountSettings()
    await selectGroup(element, 'tts')

    expect(element.querySelector('[data-testid="fetch-models-status-tts-aliyun"]')?.textContent).toContain('拉取模型列表失败')
    // The saved whitelist still renders as checked rows despite the failure.
    const box = element.querySelector('[data-testid="candidate-check-tts-aliyun-qwen-audio-3.0-tts-plus"]') as HTMLInputElement
    expect(box).not.toBeNull()
    expect(box.checked).toBe(true)
  })
})
