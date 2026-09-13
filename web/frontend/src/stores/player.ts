import { defineStore } from 'pinia'
import type { ReadyAudio, StoryCharacter, StoryLine } from '../types'

type EventRecord = Record<string, any>
export const usePlayerStore = defineStore('player', {
  state: () => ({ socket: null as WebSocket | null, phase: 'idle', message: '', title: '', characters: [] as StoryCharacter[], lines: [] as StoryLine[], currentIndex: -1, lineDurations: {} as Record<string, number>, fillerText: '', warning: '', jobId: '', finalUrl: '', audio: null as ReadyAudio | null, error: '' }),
  actions: {
    start(payload: Record<string, unknown>, onBytes: (bytes: ArrayBuffer) => void, onEvent?: (event: EventRecord) => void) {
      this.socket?.close()
      this.error = ''; this.warning = ''; this.message = ''; this.title = ''; this.characters = []; this.lines = []; this.currentIndex = -1; this.lineDurations = {}; this.fillerText = ''; this.jobId = ''; this.finalUrl = ''; this.audio = null; this.phase = 'connecting';
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = new WebSocket(`${protocol}//${location.host}/ws`); socket.binaryType = 'arraybuffer'; this.socket = socket
      socket.onopen = () => socket.send(JSON.stringify({ type: 'start', ...payload }))
      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') { onBytes(event.data); return }
        const item = JSON.parse(event.data) as EventRecord
        onEvent?.(item)
        if (item.type === 'ready') this.audio = item.audio
        if (item.type === 'status') { this.phase = item.phase; this.message = item.message || ({ queued: '排队等待中…', script: '正在生成剧本…', voices: '正在匹配音色…', line: '正在生成故事…', finalizing: '正在整理完整音频…' } as Record<string, string>)[item.phase] || item.phase }
        if (item.type === 'script_ready') { this.title = item.title; this.characters = item.characters || []; this.lines = item.lines.map((line: any) => ({...line, text: ''})) }
        if (item.type === 'line_start') { this.phase = 'line'; this.message = `正在讲第 ${item.index} / ${item.total} 句…`; this.currentIndex = item.index - 1; const line = this.lines[this.currentIndex]; if (line) line.text = item.text }
        if (item.type === 'filler_start') { this.fillerText = item.text; this.message = item.kind === 'thinking' ? '正在构思故事…' : '正在准备开场…' }
        if (item.type === 'filler_end' || item.type === 'filler_abort') this.fillerText = ''
        if (item.type === 'warning') this.warning = item.message || '这一句没有播放成功'
        if (item.type === 'line_end') { this.lineDurations[item.line_id] = item.duration_ms; this.message = '正在继续生成下一句…' }
        if (item.type === 'finalizing') { this.phase = 'finalizing'; this.message = '正在整理完整音频…' }
        if (item.type === 'complete') { this.phase = 'completed'; this.message = '故事已完成'; this.finalUrl = item.audio_url; this.jobId = item.project_id }
        if (item.type === 'error') { this.phase = 'failed'; this.message = '生成失败'; this.error = String(item.message || '未知错误').replace(/429 Client Error: Too Many Requests.*/i, '请求过于频繁，火山引擎暂时限流，请稍后再试'); console.error('[storyteller-web] generation error', item) }
        if (item.type === 'canceled') { this.phase = 'canceled'; this.message = '已停止生成' }
      }
      socket.onerror = (event) => { this.error = '连接中断，请稍后再试'; this.message = '连接中断'; this.phase = 'failed'; console.error('[storyteller-web] websocket error', event) }
    },
    cancel() { this.socket?.send(JSON.stringify({ type: 'cancel' })) },
    close() { this.socket?.close(); this.socket = null },
  },
})
