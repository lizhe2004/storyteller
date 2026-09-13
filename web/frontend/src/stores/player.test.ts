import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from './player'

describe('player script display', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps preview text when the authoritative script arrives', () => {
    const store = usePlayerStore()

    store.applyScriptReady({
      type: 'script_ready',
      title: '测试故事',
      characters: [],
      lines: [{ line_id: '1', line_type: 'narration', text: '月亮升起来了。' }],
    })

    expect(store.lines[0].text).toBe('月亮升起来了。')
  })
})
