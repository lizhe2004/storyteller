import { describe, expect, it, vi } from 'vitest'
import { useAudioTimeline } from './useAudioTimeline'
import workletSource from '../../public/assets/pcm-ring-buffer-worklet.js?raw'

class FakeAudioWorkletProcessor {
  port = { onmessage: null as ((event: { data: any }) => void) | null, postMessage: vi.fn() }
}

class FakeContext {
  currentTime = 0; state = 'running'; destination = {}
  sources: any[] = []
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn(async () => { this.state = 'suspended' })
  close = vi.fn(async () => {})
  createBuffer(_channels: number, length: number, rate: number) { return { duration: length / rate, getChannelData: () => new Float32Array(length) } as any }
  createBufferSource() { const source = { buffer: null as any, connect: vi.fn(), start: vi.fn(), onended: null as (() => void) | null }; this.sources.push(source); return source as any }
}

describe('useAudioTimeline', () => {
  it('outputs the final buffered sample and signals ended after draining', () => {
    let Processor: any
    new Function('AudioWorkletProcessor', 'sampleRate', 'registerProcessor', workletSource)(
      FakeAudioWorkletProcessor,
      24000,
      (_name: string, processor: any) => { Processor = processor },
    )
    const processor = new Processor({ processorOptions: { inputSampleRate: 24000 } })
    processor.port.onmessage({ data: { type: 'write', samples: new Float32Array([0.1, 0.2, 0.3]).buffer } })
    processor.port.onmessage({ data: { type: 'end' } })
    const channel = new Float32Array(8)

    processor.process([], [[channel]])

    expect(channel[0]).toBeCloseTo(0.1, 6)
    expect(channel[1]).toBeCloseTo(0.2, 6)
    expect(channel[2]).toBeCloseTo(0.3, 6)
    expect(channel[3]).toBe(0)
    expect(processor.port.postMessage).toHaveBeenCalledWith({ type: 'ended', playedSamples: 8 })
  })

  it('accepts PCM into the playback buffer using the ready sample rate', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(24000)
    expect((globalThis as any).AudioContext).toHaveBeenCalledWith({ sampleRate: 24000 })
    timeline.append(new Int16Array(2400).buffer)
    expect(fake.sources[0].start).toHaveBeenCalledWith(0.05)
    expect(timeline.bufferedMs.value).toBe(100)
    expect(fake.resume).toHaveBeenCalled()
  })

  it('plays PCM buffered during AudioWorklet startup if worklet loading fails', async () => {
    const fake = new FakeContext() as FakeContext & { audioWorklet: { addModule: ReturnType<typeof vi.fn> } }
    fake.audioWorklet = { addModule: vi.fn(async () => { throw new Error('worklet load failed') }) }
    ;(globalThis as any).AudioContext = vi.fn(() => fake)
    ;(globalThis as any).AudioWorkletNode = vi.fn()
    const timeline = useAudioTimeline()
    timeline.begin(24000)
    timeline.append(new Int16Array(2400).buffer)

    await vi.waitFor(() => expect(fake.sources).toHaveLength(1))
    expect(fake.sources[0].start).toHaveBeenCalledWith(0.05)
    delete (globalThis as any).AudioWorkletNode
  })

  it('can suspend and resume the same audio context', async () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(); await timeline.togglePause(); expect(fake.suspend).toHaveBeenCalled(); await timeline.togglePause(); expect(fake.resume).toHaveBeenCalledTimes(2)
  })

  it('marks fallback playback finished only after its queued audio ends', () => {
    const fake = new FakeContext(); (globalThis as any).AudioContext = vi.fn(() => fake)
    const timeline = useAudioTimeline(); timeline.begin(); timeline.append(new Int16Array(2400).buffer)

    timeline.finish()

    expect(timeline.playing.value).toBe(true)
    expect(timeline.ended.value).toBe(false)
    fake.sources[0].onended?.()
    expect(timeline.playing.value).toBe(false)
    expect(timeline.ended.value).toBe(true)
  })

  it('marks AudioWorklet playback finished when the worklet reports its end event', async () => {
    const fake = new FakeContext() as FakeContext & { audioWorklet: { addModule: ReturnType<typeof vi.fn> } }
    const node = { port: { postMessage: vi.fn(), onmessage: null as ((event: { data: { type: string } }) => void) | null }, connect: vi.fn(), disconnect: vi.fn() }
    fake.audioWorklet = { addModule: vi.fn(async () => {}) }
    ;(globalThis as any).AudioContext = vi.fn(() => fake)
    ;(globalThis as any).AudioWorkletNode = vi.fn(() => node)
    const timeline = useAudioTimeline(); timeline.begin()
    await vi.waitFor(() => expect(node.connect).toHaveBeenCalled())

    timeline.finish()
    expect(node.port.postMessage).toHaveBeenCalledWith({ type: 'end' })
    node.port.onmessage?.({ data: { type: 'ended' } })

    expect(timeline.playing.value).toBe(false)
    expect(timeline.ended.value).toBe(true)
    delete (globalThis as any).AudioWorkletNode
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
