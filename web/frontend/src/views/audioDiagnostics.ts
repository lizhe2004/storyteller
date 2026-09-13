export const PCM_SAMPLE_RATE = 24000

export function mergePcmBytes(parts: Uint8Array[]) {
  const bytes = new Uint8Array(parts.reduce((total, part) => total + part.byteLength, 0))
  let offset = 0
  for (const part of parts) {
    bytes.set(part, offset)
    offset += part.byteLength
  }
  return bytes.buffer
}

export function pcmDurationMs(byteLength: number) {
  return byteLength / 2 / PCM_SAMPLE_RATE * 1000
}

export function splitPcmByManifest(buffer: ArrayBuffer, frames: Array<{ bytes: number }>) {
  const bytes = new Uint8Array(buffer)
  const parts: ArrayBuffer[] = []
  let offset = 0
  for (const frame of frames) {
    if (!Number.isInteger(frame.bytes) || frame.bytes < 0 || frame.bytes % 2 !== 0 || offset + frame.bytes > bytes.length) throw new Error('PCM 与 manifest 的帧大小不匹配')
    parts.push(bytes.slice(offset, offset + frame.bytes).buffer)
    offset += frame.bytes
  }
  if (offset !== bytes.length) throw new Error('PCM 与 manifest 的总字节数不匹配')
  return parts
}

export function pcmBytesToFloat32(buffer: ArrayBuffer) {
  if (buffer.byteLength % 2 !== 0) throw new Error('PCM frame 大小不是 16-bit 采样点的整数倍')
  const input = new Int16Array(buffer)
  const output = new Float32Array(input.length)
  for (let i = 0; i < input.length; i += 1) output[i] = input[i] / 32768
  return output
}
