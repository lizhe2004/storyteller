import { createApp, nextTick, type App } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { usePlayerStore } from '../stores/player'
import HomeView from './HomeView.vue'

const mounted: { app: App; element: HTMLElement }[] = []

async function mountHome(pinia = createPinia()) {
  vi.spyOn(api, 'options').mockResolvedValue({ lengths: ['short'], complexities: ['simple'], tts_providers: [], sound_enabled: false })
  const element = document.createElement('div')
  document.body.appendChild(element)
  const app = createApp(HomeView).use(pinia)
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
  vi.unstubAllGlobals()
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

  it('reconnects the MP3 job when returning from the background without restarting audio', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      binaryType = ''
      onmessage: ((event: { data: string | ArrayBuffer }) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      constructor(readonly url: string) { MockWebSocket.instances.push(this) }
      close() {}
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
    const pinia = createPinia()
    const player = usePlayerStore(pinia)
    player.applyEvent({ type: 'ready', job_id: 'job_mobile', audio: {} })
    const element = await mountHome(pinia)
    const mode = element.querySelector('select[aria-label="播放方式"]') as HTMLSelectElement
    mode.value = 'native_mp3'
    mode.dispatchEvent(new Event('change', { bubbles: true }))
    await nextTick()

    const originalVisibility = Object.getOwnPropertyDescriptor(document, 'visibilityState')
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('/ws?job_id=job_mobile')
    if (originalVisibility) Object.defineProperty(document, 'visibilityState', originalVisibility)
    else delete (document as Document & { visibilityState?: string }).visibilityState
  })

  it('waits for job completion after MP3 playback ends, then enables replay and hides stop generation', async () => {
    const pinia = createPinia()
    const player = usePlayerStore(pinia)
    player.title = '后台播放测试'
    player.phase = 'line'
    player.streamJobId = 'job_mobile'
    const element = await mountHome(pinia)
    const mode = element.querySelector('select[aria-label="播放方式"]') as HTMLSelectElement
    mode.value = 'native_mp3'
    mode.dispatchEvent(new Event('change', { bubbles: true }))
    const audio = element.querySelector('audio') as HTMLAudioElement
    audio.play = vi.fn().mockResolvedValue()
    audio.load = vi.fn()
    audio.dispatchEvent(new Event('ended'))
    await nextTick()

    const pendingButton = element.querySelector('.round') as HTMLButtonElement
    expect(pendingButton.disabled).toBe(true)
    expect(pendingButton.getAttribute('aria-label')).toBe('等待故事完成')
    expect(element.textContent).toContain('停止生成')

    player.applyEvent({ type: 'complete', project_id: 'proj_mobile', audio_url: '/api/stories/proj_mobile/audio' })
    await nextTick()

    const replayButton = element.querySelector('.round') as HTMLButtonElement
    expect(element.textContent).not.toContain('停止生成')
    expect(replayButton.disabled).toBe(false)
    expect(replayButton.getAttribute('aria-label')).toBe('重新播放')
    replayButton.click()
    expect(audio.play).toHaveBeenCalledOnce()
    expect(audio.src).toContain('/api/stories/proj_mobile/audio')
  })

})
