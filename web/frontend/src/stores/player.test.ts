import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from './player'

function scriptReady(store: ReturnType<typeof usePlayerStore>) {
  store.applyScriptReady({
    type: 'script_ready',
    title: '深夜小木屋',
    characters: [],
    lines: [
      { line_id: 'l1', line_type: 'narration', speaker: '旁白', text: '' },
      { line_id: 'l2', line_type: 'dialogue', speaker: '小熊', text: '' },
    ],
  })
}

describe('player script display', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.unstubAllGlobals())

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

  it('does not let a late script preview erase matched character voices', () => {
    const store = usePlayerStore()
    const voice = { provider: 'volcengine', voice_id: 'voice-fox', name: '亮嗓萌仔' }
    store.applyScriptReady({
      type: 'script_ready',
      title: '冬夜小狐狸',
      characters: [{ id: 'fox', name: '小狐狸', voice }],
      lines: [{ line_id: '1', line_type: 'dialogue', character_id: 'fox', speaker: '小狐狸', text: '回家吧。' }],
    })

    store.applyScriptPreview({
      type: 'script_preview',
      title: '冬夜小狐狸',
      characters: [{ id: 'fox', name: '小狐狸' }],
      lines: [{ line_id: '1', line_type: 'dialogue', character_id: 'fox', speaker: '小狐狸', text: '回家吧。' }],
    })

    expect(store.characters[0].voice).toEqual(voice)
  })

  it('applies matched voices before script_ready and carries them across later previews', () => {
    const store = usePlayerStore()
    const voice = { provider: 'volcengine', voice_id: 'voice-fox', name: '亮嗓萌仔' }
    store.applyScriptPreview({
      type: 'script_preview',
      title: '冬夜小狐狸',
      characters: [{ id: 'fox', name: '小狐狸' }],
      lines: [],
    })

    store.applyEvent({
      type: 'characters_matched',
      characters: [{ id: 'fox', name: '小狐狸', voice }],
    })
    expect(store.characters[0].voice).toEqual(voice)

    store.applyScriptPreview({
      type: 'script_preview',
      title: '冬夜小狐狸',
      characters: [{ id: 'fox', name: '小狐狸' }],
      lines: [],
    })

    expect(store.characters[0].voice).toEqual(voice)
  })
})

describe('player opening / start notice events', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('accumulates opening text deltas into the host bubble', () => {
    const store = usePlayerStore()

    store.applyEvent({ type: 'opening_text_delta', text: '夜幕' })
    expect(store.fillerText).toBe('夜幕')
    store.applyEvent({ type: 'opening_text_delta', text: '降临' })
    expect(store.fillerText).toBe('夜幕降临')
  })

  it('clears the host bubble when opening audio ends or aborts', () => {
    const store = usePlayerStore()
    store.applyEvent({ type: 'opening_text_delta', text: '夜幕降临，森林安静下来。' })
    expect(store.fillerText).not.toBe('')

    store.applyEvent({ type: 'opening_audio_end', duration_ms: 3200 })
    expect(store.fillerText).toBe('')

    store.applyEvent({ type: 'opening_text_delta', text: '又一段开场' })
    store.applyEvent({ type: 'opening_audio_abort' })
    expect(store.fillerText).toBe('')
  })

  it('shows the fixed start notice after opening and before lines', () => {
    const store = usePlayerStore()

    store.applyEvent({ type: 'opening_text_delta', text: '开场' })
    store.applyEvent({ type: 'opening_audio_end', duration_ms: 1000 })
    store.applyEvent({ type: 'start_notice', text: '故事就要开始喽' })

    expect(store.fillerText).toBe('故事就要开始喽')
  })

  it('updates line text from line_text_delta and clears the bubble on the first line', () => {
    const store = usePlayerStore()
    scriptReady(store)
    store.applyEvent({ type: 'start_notice', text: '故事就要开始喽' })

    store.applyEvent({ type: 'line_start', line_id: 'l1', index: 1, total: 2, text: '风呼呼地吹。' })
    expect(store.fillerText).toBe('')
    expect(store.currentIndex).toBe(0)

    // A suffix delta extends the line; a full-text delta that already contains it is idempotent.
    store.applyEvent({ type: 'line_text_delta', line_id: 'l1', index: 1, text: '风呼呼地吹。' })
    expect(store.lines[0].text).toBe('风呼呼地吹。')
    store.applyEvent({ type: 'line_text_delta', line_id: 'l2', index: 2, text: '谁在外面？' })
    expect(store.lines[1].text).toBe('谁在外面？')
  })

  it('reaches completion through the new event sequence without legacy thinking events', () => {
    const store = usePlayerStore()

    store.applyEvent({ type: 'ready', audio: { encoding: 'pcm_s16le', sample_rate: 24000, channels: 1 } })
    store.applyEvent({ type: 'status', phase: 'script', message: '正在生成剧本…' })
    store.applyEvent({ type: 'opening_text_delta', text: '很久很久以前，' })
    store.applyEvent({ type: 'opening_audio_start' })
    store.applyEvent({ type: 'opening_text_delta', text: '有一间小木屋。' })
    store.applyEvent({ type: 'opening_audio_end', duration_ms: 2500 })
    scriptReady(store)
    store.applyEvent({ type: 'start_notice', text: '故事就要开始喽' })
    store.applyEvent({ type: 'line_start', line_id: 'l1', index: 1, total: 2, text: '风呼呼地吹。' })
    store.applyEvent({ type: 'line_text_delta', line_id: 'l1', index: 1, text: '风呼呼地吹。' })
    store.applyEvent({ type: 'line_end', line_id: 'l1', duration_ms: 2000 })
    store.applyEvent({ type: 'finalizing' })
    store.applyEvent({
      type: 'complete',
      project_id: 'proj_1',
      title: '深夜小木屋',
      audio_url: '/api/stories/proj_1/audio',
    })

    expect(store.phase).toBe('completed')
    expect(store.finalUrl).toBe('/api/stories/proj_1/audio')
    expect(store.jobId).toBe('proj_1')
    expect(store.fillerText).toBe('')
  })

  it('remembers the job id from ready so the same streamed story can be recovered after backgrounding', () => {
    const store = usePlayerStore()

    store.applyEvent({ type: 'ready', job_id: 'job_recover_me', audio: { encoding: 'pcm_s16le', sample_rate: 24000, channels: 1 } })

    expect(store.streamJobId).toBe('job_recover_me')
  })

  it('restores the full script and terminal URL from a recovered job socket', () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      binaryType = ''
      onmessage: ((event: { data: string | ArrayBuffer }) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      closed = false
      constructor(readonly url: string) { MockWebSocket.instances.push(this) }
      close() { this.closed = true }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
    const store = usePlayerStore()
    store.applyEvent({ type: 'ready', job_id: 'job_recover_me', audio: {} })
    const onEvent = vi.fn()

    expect(store.reconnect(() => {}, onEvent)).toBe(true)
    const socket = MockWebSocket.instances[0]
    expect(socket.url).toContain('/ws?job_id=job_recover_me')
    socket.onmessage?.({ data: JSON.stringify({
      type: 'script_ready', title: '后台播放的故事', characters: [],
      lines: [{ line_id: 'l1', line_type: 'narration', speaker: '旁白', text: '返回前没有显示的完整台词。' }],
    }) })
    socket.onmessage?.({ data: JSON.stringify({
      type: 'complete', project_id: 'proj_1', audio_url: '/api/stories/proj_1/audio',
    }) })

    expect(store.lines[0].text).toBe('返回前没有显示的完整台词。')
    expect(store.phase).toBe('completed')
    expect(store.terminalEventReceived).toBe(true)
    expect(store.finalUrl).toBe('/api/stories/proj_1/audio')
  })

  it('still completes formal lines when opening is missing/aborted', () => {
    const store = usePlayerStore()

    store.applyEvent({ type: 'opening_audio_abort' })
    scriptReady(store)
    store.applyEvent({ type: 'start_notice', text: '故事就要开始喽' })
    store.applyEvent({ type: 'line_start', line_id: 'l1', index: 1, total: 1, text: '正式第一句。' })
    store.applyEvent({ type: 'line_end', line_id: 'l1', duration_ms: 1500 })

    expect(store.currentIndex).toBe(0)
    expect(store.lines[0].text).toBe('正式第一句。')
  })
})
