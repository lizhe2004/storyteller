import { describe, expect, it } from 'vitest'
import { mergePcmBytes, pcmBytesToFloat32, pcmDurationMs, splitPcmByManifest } from './audioDiagnostics'

describe('audio diagnostics helpers', () => {
  it('merges uploaded s16le PCM parts without changing sample order', () => {
    const merged = mergePcmBytes([new Uint8Array([1, 0]), new Uint8Array([2, 0, 3, 0])])
    expect(Array.from(new Int16Array(merged))).toEqual([1, 2, 3])
  })

  it('calculates duration from the fixed 24kHz mono input format', () => {
    expect(pcmDurationMs(48000)).toBe(1000)
  })

  it('splits a PCM file according to the original frame byte lengths', () => {
    const parts = splitPcmByManifest(new Uint8Array([1, 2, 3, 4, 5, 6]).buffer, [{ bytes: 2 }, { bytes: 4 }])
    expect(parts.map(part => Array.from(new Uint8Array(part)))).toEqual([[1, 2], [3, 4, 5, 6]])
  })

  it('converts each s16le frame to the Float32 format expected by the Worklet', () => {
    const converted = pcmBytesToFloat32(new Int16Array([-32768, 0, 16384]).buffer)
    expect(Array.from(converted)).toEqual([-1, 0, 0.5])
  })
})
