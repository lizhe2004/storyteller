import { createApp, nextTick, type App } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import HomeView from './HomeView.vue'

const mounted: { app: App; element: HTMLElement }[] = []

async function mountHome(withModels = false) {
  vi.spyOn(api, 'options').mockResolvedValue({
    lengths: ['short'], complexities: ['simple'], tts_providers: [], sound_enabled: false,
    llm_models: withModels ? [{ provider: 'mock', model: 'story-v1', label: 'mock / story-v1' }] : [],
    audio_models: withModels ? [{ provider: 'mock', model: 'voice-v1', label: 'mock / voice-v1' }] : [],
  })
  const element = document.createElement('div')
  document.body.appendChild(element)
  const app = createApp(HomeView).use(createPinia())
  app.mount(element)
  mounted.push({ app, element })
  await nextTick()
  return element
}

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
  vi.restoreAllMocks()
})

describe('HomeView empty state', () => {
  it('offers both playback modes and keeps Web Audio as the default', async () => {
    const element = await mountHome()
    const select = element.querySelector('select[aria-label="播放方式"]') as HTMLSelectElement

    expect(select.value).toBe('webaudio')
    expect(Array.from(select.options).map(option => option.value)).toEqual(['webaudio', 'native_mp3'])
  })

  it('offers a story idea that fills and focuses the topic field', async () => {
    const element = await mountHome()
    const textarea = element.querySelector('#topic') as HTMLTextAreaElement

    expect(element.querySelectorAll('[data-testid="story-idea"]')).toHaveLength(3)
    ;(element.querySelector('[data-testid="story-idea"]') as HTMLButtonElement).click()
    await nextTick()

    expect(textarea.value).toBe('一只怕黑的小狐狸，在月亮下交到了朋友')
    expect(document.activeElement).toBe(textarea)
  })

  it('shows per-story LLM and audio model selectors when configured', async () => {
    const element = await mountHome(true)
    const selects = Array.from(element.querySelectorAll('.model-row select')) as HTMLSelectElement[]

    expect(selects).toHaveLength(2)
    expect(selects[0].value).toBe('mock::story-v1')
    expect(selects[1].value).toBe('mock::voice-v1')
  })

})
