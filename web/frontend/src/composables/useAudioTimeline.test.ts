import { describe, expect, it, vi } from 'vitest'
import { useAudioTimeline } from './useAudioTimeline'

class FakeContext {
  currentTime = 0; state = 'running'; destination = {}
  sources: any[] = []
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn(async () => { this.state = 'suspended' })
  close = vi.fn(async () => {})
  createBuffer(_channels: number, length: number, rate: number) { return { duration: length / rate, getChannelData: () => new Float32Array(length) } as any }
  createBufferSource() { const source = { buffer: null as any, connect: vi.fn(), start: vi.fn() }; this.sources.push(source); return source as any }
}

describe('useAudioTimeline', () => {
  it('accepts PCM into the playback buffer using the ready sample rate', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(24000)
    expect((globalThis as any).AudioContext).toHaveBeenCalledWith({ sampleRate: 24000 })
    timeline.append(new Int16Array(2400).buffer)
    expect(fake.sources[0].start).toHaveBeenCalledWith(0.05)
    expect(timeline.bufferedMs.value).toBe(100)
    expect(fake.resume).toHaveBeenCalled()
  })

  it('can suspend and resume the same audio context', async () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(); await timeline.togglePause(); expect(fake.suspend).toHaveBeenCalled(); await timeline.togglePause(); expect(fake.resume).toHaveBeenCalledTimes(2)
  })

  it('does not report a false underrun when the fallback queue has buffered PCM', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const timeline = useAudioTimeline(); timeline.begin(); timeline.setUnit('line:L2')
    timeline.append(new Int16Array(2400).buffer)
    fake.currentTime = 0.2
    timeline.append(new Int16Array(2400).buffer)
    expect(warning).not.toHaveBeenCalledWith('[storyteller-audio] PCM underrun / gap', expect.anything())
    expect(timeline.underruns.value).toBe(0)
    warning.mockRestore()
  })

  it('can replay the captured PCM without creating a new story', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(24000)
    timeline.append(new Int16Array(2400).buffer)

    timeline.replay()

    expect((globalThis as any).AudioContext).toHaveBeenCalledTimes(2)
    expect(fake.sources).toHaveLength(2)
    expect(fake.sources[1].start).toHaveBeenCalledWith(0.05)
    expect(timeline.bufferedMs.value).toBe(100)
  })

  it('can replay the captured PCM as one continuous AudioBuffer for comparison', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(24000)
    timeline.append(new Int16Array(2400).buffer)

    timeline.replayDirect()

    expect(fake.sources).toHaveLength(2)
    expect(fake.sources[1].buffer.duration).toBe(0.1)
    expect(fake.sources[1].start).toHaveBeenCalledWith(0.05)
  })
})
