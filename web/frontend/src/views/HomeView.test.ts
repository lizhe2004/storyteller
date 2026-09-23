import { createApp, nextTick, type App } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { usePlayerStore } from '../stores/player'
import HomeView from './HomeView.vue'
import type { ModelOption } from '../types'

const mounted: { app: App; element: HTMLElement }[] = []
const storage = new Map<string, string>()

beforeEach(() => {
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) || null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
  })
})

async function mountHome(withModels = false, audioOptions?: ModelOption[], llmOptions?: ModelOption[]) {
  vi.spyOn(api, 'options').mockResolvedValue({
    lengths: ['short'], complexities: ['simple'], tts_providers: [], sound_enabled: false,
    llm_models: llmOptions || (withModels ? [{ provider: 'mock', model: 'story-v1', label: 'mock / story-v1', is_default: true }] : []),
    audio_models: audioOptions || (withModels ? [{ provider: 'mock', model: 'voice-v1', label: 'mock / voice-v1' }] : []),
  })
  const element = document.createElement('div')
  document.body.appendChild(element)
  const pinia = createPinia()
  const player = usePlayerStore(pinia)
  const app = createApp(HomeView).use(pinia)
  app.mount(element)
  mounted.push({ app, element })
  await nextTick()
  return { element, player }
}

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
  vi.restoreAllMocks()
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('HomeView empty state', () => {
  it('offers both playback modes and keeps Web Audio as the default', async () => {
    const { element } = await mountHome()
    const select = element.querySelector('select[aria-label="播放方式"]') as HTMLSelectElement

    expect(select.value).toBe('webaudio')
    expect(Array.from(select.options).map(option => option.value)).toEqual(['webaudio', 'native_mp3'])
  })

  it('offers a story idea that fills and focuses the topic field', async () => {
    const { element } = await mountHome()
    const textarea = element.querySelector('#topic') as HTMLTextAreaElement

    expect(element.querySelectorAll('[data-testid="story-idea"]')).toHaveLength(3)
    ;(element.querySelector('[data-testid="story-idea"]') as HTMLButtonElement).click()
    await nextTick()

    expect(textarea.value).toBe('一只怕黑的小狐狸，在月亮下交到了朋友')
    expect(document.activeElement).toBe(textarea)
  })

  it('shows per-story LLM and audio model selectors when configured', async () => {
    const { element } = await mountHome(true)
    const selects = Array.from(element.querySelectorAll('.model-row select')) as HTMLSelectElement[]

    expect(selects).toHaveLength(1)
    expect(selects[0].value).toBe('mock::story-v1')
    expect(element.querySelector('[data-testid="audio-model-trigger"]')).toBeTruthy()
    expect(element.querySelector('[data-testid="audio-model-menu"]')).toBeNull()
    ;(element.querySelector('[data-testid="audio-model-trigger"]') as HTMLButtonElement).click()
    await nextTick()
    const checkboxes = Array.from(element.querySelectorAll('[data-testid="audio-model-option"] input')) as HTMLInputElement[]
    expect(checkboxes).toHaveLength(1)
    expect(checkboxes[0].checked).toBe(true)
    document.body.click()
    await nextTick()
    expect(element.querySelector('[data-testid="audio-model-menu"]')).toBeNull()
    expect(selects[0].textContent).toContain('（默认）')
  })

  it('restores the saved audio model selection from local storage', async () => {
    localStorage.setItem('storyteller.home.audio-models', JSON.stringify(['mock::voice-v2']))
    const { element } = await mountHome(true, [
      { provider: 'mock', model: 'voice-v1', label: 'mock / voice-v1' },
      { provider: 'mock', model: 'voice-v2', label: 'mock / voice-v2' },
    ])

    ;(element.querySelector('[data-testid="audio-model-trigger"]') as HTMLButtonElement).click()
    await nextTick()
    const checkboxes = Array.from(element.querySelectorAll('[data-testid="audio-model-option"] input')) as HTMLInputElement[]
    expect(checkboxes.map(input => input.checked)).toEqual([false, true])
    checkboxes[1].click()
    await nextTick()
    expect(JSON.parse(localStorage.getItem('storyteller.home.audio-models') || 'null')).toEqual([])
  })

  it('restores the saved LLM model selection from local storage', async () => {
    localStorage.setItem('storyteller.home.llm-model', 'mock::story-v2')
    const { element } = await mountHome(true, undefined, [
      { provider: 'mock', model: 'story-v1', label: 'mock / story-v1', is_default: true },
      { provider: 'mock', model: 'story-v2', label: 'mock / story-v2' },
    ])

    const llmSelect = element.querySelector('.model-row select') as HTMLSelectElement
    expect(llmSelect.value).toBe('mock::story-v2')
  })

  it('shows the matched provider and a voice detail popover on focus', async () => {
    const { element, player } = await mountHome()
    player.title = '测试故事'
    player.characters = [{
      id: 'fox',
      name: '小狐狸',
      description: '一只怕黑、正在寻找朋友的小狐狸',
      gender: 'female',
      age: 'child',
      voice: {
        provider: 'aliyun',
        model: 'qwen-tts-latest',
        voice_id: 'longanlingxin',
        name: '龙安灵心',
        gender: 'female',
        age: ['child', 'teen'],
        category: '社交陪伴',
        description: '温暖亲和的故事女声',
      },
    }]
    await nextTick()

    const chip = element.querySelector('[data-testid="character-chip"]') as HTMLElement
    const characterSummary = chip.querySelector('[data-testid="character-summary"]') as HTMLElement
    expect(characterSummary.textContent).toContain('小狐狸')
    expect(characterSummary.textContent).toContain('一只怕黑、正在寻找朋友的小狐狸')
    expect(characterSummary.textContent).toContain('女')
    expect(characterSummary.textContent).toContain('儿童')
    expect(characterSummary.textContent).not.toContain('aliyun')
    expect(chip.querySelector('[data-testid="voice-popover"]')).not.toBeNull()
    chip.focus()
    await nextTick()
    const popover = chip.querySelector('[data-testid="voice-popover"]') as HTMLElement
    expect(popover.textContent).toContain('aliyun')
    expect(popover.textContent).toContain('qwen-tts-latest')
    expect(popover.textContent).toContain('龙安灵心')
    expect(popover.textContent).toContain('女')
    expect(popover.textContent).toContain('儿童')
    expect(popover.textContent).toContain('少年')
    expect(popover.textContent).toContain('社交陪伴')
    expect(popover.textContent).toContain('温暖亲和的故事女声')
  })

  it('renders a legacy scalar voice age from an older server', async () => {
    const { element, player } = await mountHome()
    player.title = '旧事件'
    player.characters = [{
      id: 'legacy',
      name: '旧角色',
      voice: {
        provider: 'mock',
        voice_id: 'legacy_voice',
        age: 'young_adult' as unknown as string[],
      },
    }]
    await nextTick()

    const popover = element.querySelector('[data-testid="voice-popover"]') as HTMLElement
    expect(popover.textContent).toContain('青年')
  })

  it('renders child and teen voice ages with the canonical labels', async () => {
    const { element, player } = await mountHome()
    player.title = '测试故事'
    player.characters = [
      {
        id: 'child', name: '小孩', description: '儿童角色', gender: 'female', age: 'child',
        voice: { provider: 'mock', model: 'voice-child', voice_id: 'child', name: '童声', gender: 'female', age: 'child' },
      },
      {
        id: 'teen', name: '少年', description: '少年角色', gender: 'male', age: 'teen',
        voice: { provider: 'mock', model: 'voice-teen', voice_id: 'teen', name: '少年声', gender: 'male', age: 'teen' },
      },
    ]
    await nextTick()

    const chips = Array.from(element.querySelectorAll('[data-testid="character-chip"]')) as HTMLElement[]
    expect(chips).toHaveLength(2)
    expect(chips[0].querySelector('[data-testid="character-summary"] small:last-child')?.textContent).toBe('女 · 儿童')
    expect(chips[1].querySelector('[data-testid="character-summary"] small:last-child')?.textContent).toBe('男 · 少年')
    expect(chips[1].querySelector('[data-testid="voice-popover"] dd:nth-of-type(5)')?.textContent).toBe('少年')
  })

  it('keeps unknown legacy age labels unchanged for compatibility', async () => {
    const { element, player } = await mountHome()
    player.title = '测试故事'
    player.characters = [{
      id: 'legacy', name: '旧角色', description: '兼容测试', gender: 'female', age: 'child',
      voice: { provider: 'mock', model: 'voice-legacy', voice_id: 'legacy', name: '旧音色', gender: 'female', age: '青少年' },
    }]
    await nextTick()

    expect(element.querySelector('[data-testid="voice-popover"]')?.textContent).toContain('青少年')
  })

})
