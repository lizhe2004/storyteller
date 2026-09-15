import { defineStore } from 'pinia'
import type { ReadyAudio, StoryCharacter, StoryLine } from '../types'

type EventRecord = Record<string, any>
export const usePlayerStore = defineStore('player', {
  state: () => ({ socket: null as WebSocket | null, phase: 'idle', message: '', title: '', characters: [] as StoryCharacter[], lines: [] as StoryLine[], currentIndex: -1, lineDurations: {} as Record<string, number>, openingText: '', fillerText: '', noticeText: '', warning: '', jobId: '', finalUrl: '', audio: null as ReadyAudio | null, error: '', previewFrame: null as number | null, pendingPreview: null as EventRecord | null }),
  actions: {
    applyScriptPreview(item: EventRecord) {
      this.title = item.title || this.title
      this.characters = item.characters || this.characters
      this.lines = (item.lines || []).map((line: any) => ({...line}))
    },
    scheduleScriptPreview(item: EventRecord) {
      this.pendingPreview = item
      if (this.previewFrame !== null) return
      this.previewFrame = window.requestAnimationFrame(() => {
        const preview = this.pendingPreview
        this.pendingPreview = null
        this.previewFrame = null
        if (preview) this.applyScriptPreview(preview)
      })
    },
    applyScriptReady(item: EventRecord) {
      if (this.previewFrame !== null) {
        window.cancelAnimationFrame(this.previewFrame)
        this.previewFrame = null
      }
      this.pendingPreview = null
      this.title = item.title
      this.characters = item.characters || []
      this.lines = (item.lines || []).map((line: any) => ({...line, text: line.text || ''}))
    },
    applyLineTextDelta(item: EventRecord) {
      const line = this.lines.find((entry) => entry.line_id === item.line_id)
        || (typeof item.index === 'number' ? this.lines[item.index - 1] : undefined)
      if (!line) return
      const incoming = String(item.text || '')
      if (!incoming) return
      if (!line.text) line.text = incoming
      else if (incoming.startsWith(line.text)) line.text = incoming      // suffix / growing full text
      else if (!line.text.startsWith(incoming)) line.text += incoming   // pure suffix delta
    },
    applyEvent(item: EventRecord) {
      if (item.type === 'ready') this.audio = item.audio
      if (item.type === 'status') { this.phase = item.phase; this.message = item.message || ({ queued: '排队等待中…', script: '正在生成剧本…', voices: '正在匹配音色…', line: '正在生成故事…', finalizing: '正在整理完整音频…' } as Record<string, string>)[item.phase] || item.phase }
      if (item.type === 'script_preview') this.scheduleScriptPreview(item)
      if (item.type === 'script_ready') this.applyScriptReady(item)
      // Opening narration streams in while the rest of the script is still being written.
      if (item.type === 'opening_text_delta') {
        this.openingText += String(item.text || '')
        this.fillerText = this.openingText
        if (this.phase === 'script' || this.phase === 'connecting') this.message = '正在写开场…'
      }
      if (item.type === 'opening_audio_start') this.message = '正在播放开场…'
      if (item.type === 'opening_audio_end' || item.type === 'opening_audio_abort') {
        this.openingText = ''
        this.fillerText = ''
      }
      // Fixed host clip between the opening and the first formal line.
      if (item.type === 'start_notice') {
        this.noticeText = String(item.text || '')
        this.fillerText = this.noticeText
        this.message = '故事就要开始喽…'
      }
      if (item.type === 'line_start') {
        this.phase = 'line'; this.message = `正在讲第 ${item.index} / ${item.total} 句…`
        this.currentIndex = item.index - 1
        this.openingText = ''; this.noticeText = ''; this.fillerText = ''
        const line = this.lines[this.currentIndex]
        if (line && item.text) line.text = item.text
      }
      if (item.type === 'line_text_delta') this.applyLineTextDelta(item)
      if (item.type === 'warning') this.warning = item.message || '这一句没有播放成功'
      if (item.type === 'line_end') { this.lineDurations[item.line_id] = item.duration_ms; this.message = '正在继续生成下一句…' }
      if (item.type === 'finalizing') { this.phase = 'finalizing'; this.message = '正在整理完整音频…' }
      if (item.type === 'complete') { this.phase = 'completed'; this.message = '故事已完成'; this.finalUrl = item.audio_url; this.jobId = item.project_id }
      if (item.type === 'error') { this.phase = 'failed'; this.message = '生成失败'; this.error = String(item.message || '未知错误').replace(/429 Client Error: Too Many Requests.*/i, '请求过于频繁，火山引擎暂时限流，请稍后再试'); console.error('[storyteller-web] generation error', item) }
      if (item.type === 'canceled') { this.phase = 'canceled'; this.message = '已停止生成' }
    },
    start(payload: Record<string, unknown>, onBytes: (bytes: ArrayBuffer) => void, onEvent?: (event: EventRecord) => void) {
      this.socket?.close()
      this.error = ''; this.warning = ''; this.message = ''; this.title = ''; this.characters = []; this.lines = []; this.currentIndex = -1; this.lineDurations = {}; this.openingText = ''; this.fillerText = ''; this.noticeText = ''; this.jobId = ''; this.finalUrl = ''; this.audio = null; this.phase = 'connecting'; this.pendingPreview = null; if (this.previewFrame !== null) { window.cancelAnimationFrame(this.previewFrame); this.previewFrame = null }
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = new WebSocket(`${protocol}//${location.host}/ws`); socket.binaryType = 'arraybuffer'; this.socket = socket
      socket.onopen = () => socket.send(JSON.stringify({ type: 'start', ...payload }))
      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') { onBytes(event.data); return }
        const item = JSON.parse(event.data) as EventRecord
        onEvent?.(item)
        this.applyEvent(item)
      }
      socket.onerror = (event) => { this.error = '连接中断，请稍后再试'; this.message = '连接中断'; this.phase = 'failed'; console.error('[storyteller-web] websocket error', event) }
    },
    cancel() { this.socket?.send(JSON.stringify({ type: 'cancel' })) },
    close() { this.socket?.close(); this.socket = null },
  },
})
