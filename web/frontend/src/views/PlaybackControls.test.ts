import { createApp, nextTick, type App } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import * as audioTimelineModule from '../composables/useAudioTimeline'
import { useAudioTimeline } from '../composables/useAudioTimeline'
import { usePlayerStore } from '../stores/player'
import HomeView from './HomeView.vue'

const mounted: { app: App; element: HTMLElement }[] = []

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
  vi.restoreAllMocks()
})

describe('playback controls', () => {
  it('updates the playback button label, icon, and appearance when paused', async () => {
    const pinia = createPinia()
    const player = usePlayerStore(pinia)
    player.title = '月亮下的小狐狸'
    player.phase = 'line'
    const timeline = useAudioTimeline()
    vi.spyOn(audioTimelineModule, 'useAudioTimeline').mockReturnValue(timeline)
    vi.spyOn(api, 'options').mockResolvedValue({ lengths: ['short'], complexities: ['simple'], tts_providers: [], sound_enabled: false })
    const element = document.createElement('div')
    document.body.appendChild(element)
    const app = createApp(HomeView).use(pinia)
    app.mount(element)
    mounted.push({ app, element })
    timeline.playing.value = true
    await nextTick()

    const button = element.querySelector('.round') as HTMLButtonElement
    expect(button.getAttribute('aria-label')).toBe('暂停播放')
    expect(button.getAttribute('aria-pressed')).toBe('true')
    expect(button.classList.contains('is-playing')).toBe(true)
    expect(button.textContent).toContain('Ⅱ')

    timeline.playing.value = false
    await nextTick()

    expect(button.getAttribute('aria-label')).toBe('继续播放')
    expect(button.getAttribute('aria-pressed')).toBe('false')
    expect(button.classList.contains('is-playing')).toBe(false)
    expect(button.textContent).toContain('▶')

    player.phase = 'completed'
    timeline.playing.value = true
    await nextTick()
    expect(element.querySelector('.round')).not.toBeNull()

    timeline.playing.value = false
    timeline.paused.value = true
    await nextTick()
    expect(element.querySelector('.round')).not.toBeNull()
    expect(element.querySelector('.round')?.getAttribute('aria-label')).toBe('继续播放')

    timeline.paused.value = false
    timeline.hasCapturedAudio.value = true
    timeline.ended.value = true
    await nextTick()
    const replayButton = element.querySelector('.round') as HTMLButtonElement
    expect(replayButton.getAttribute('aria-label')).toBe('重新播放')
    expect(replayButton.textContent).toContain('↻')
    const replay = vi.spyOn(timeline, 'replay').mockReturnValue(true)
    replayButton.click()
    expect(replay).toHaveBeenCalledOnce()
  })
})
