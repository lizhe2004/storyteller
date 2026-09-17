import { ref, computed } from 'vue'

type AudioContextWithWorklet = AudioContext & { audioWorklet?: { addModule(url: string): Promise<void> } }

export function useAudioTimeline() {
  const context = ref<AudioContext | null>(null)
  const cursor = ref(0); const played = ref(0); const buffered = ref(0); const paused = ref(false); const playing = ref(false)
  const hasCapturedAudio = ref(false)
  const underruns = ref(0)
  let sampleRate = 24000; let unit = 'unknown'; let previousUnit: string | null = null
  let frameCount = 0; let previousLastSample: number | null = null; let previousArrivalMs: number | null = null
  let worklet: AudioWorkletNode | null = null; let workletReady: Promise<void> | null = null; let useWorklet = false
  let pending: Float32Array[] = []; let queuedSamples = 0; let totalPlayedMs = 0; let storyStartMs: number | null = null; let reportedWorkletUnderruns = 0
  type AudioDiagnostics = { download: () => void; downloadPcm: () => void; downloadManifest: () => void }
  let captureParts: Uint8Array[] = []; let captureBytes = 0; let captureTruncated = false; let captureStartedAt = ''
  const maxCaptureBytes = 200 * 1024 * 1024

  function canUseWorklet(audioContext: AudioContextWithWorklet) {
    return Boolean(audioContext.audioWorklet && typeof AudioWorkletNode !== 'undefined')
  }

  function flushPending() {
    if (!worklet) return
    for (const samples of pending) worklet.port.postMessage({ type: 'write', samples: samples.buffer }, [samples.buffer])
    pending = []
  }

  function scheduleFallback(samples: Float32Array) {
    const audioContext = context.value
    if (!audioContext || !samples.length) return
    const audio = audioContext.createBuffer(1, samples.length, sampleRate)
    audio.getChannelData(0).set(samples)
    const source = audioContext.createBufferSource()
    source.buffer = audio
    source.connect(audioContext.destination)
    const at = Math.max(audioContext.currentTime + 0.05, cursor.value)
    source.start(at)
    cursor.value = at + audio.duration
  }

  function begin(rate = 24000) {
    sampleRate = rate
    if (context.value) {
      worklet?.port.postMessage({ type: 'reset' })
      worklet?.disconnect()
      void context.value.close()
      context.value = null
    }
    if (!context.value) {
      try {
        context.value = new AudioContext({ sampleRate })
      } catch {
        context.value = new AudioContext()
        console.warn('[storyteller-audio] Requested PCM sample rate is not supported; browser resampling remains enabled', { requestedSampleRate: sampleRate, actualSampleRate: context.value.sampleRate })
      }
    }
    const audioContext = context.value as AudioContextWithWorklet
    console.info('[storyteller-audio] AudioContext configured', { inputSampleRate: sampleRate, outputSampleRate: audioContext.sampleRate, nativeRate: audioContext.sampleRate === sampleRate })
    void audioContext.resume()
    cursor.value = audioContext.currentTime; paused.value = false; playing.value = true; frameCount = 0
    previousUnit = null; previousLastSample = null; previousArrivalMs = null; pending = []; queuedSamples = 0; totalPlayedMs = 0; storyStartMs = null; played.value = 0; reportedWorkletUnderruns = 0; underruns.value = 0
    captureParts = []; captureManifest.length = 0; captureBytes = 0; captureTruncated = false; captureStartedAt = new Date().toISOString()
    hasCapturedAudio.value = false
    ;(window as Window & { __storytellerAudioDiagnostics?: AudioDiagnostics }).__storytellerAudioDiagnostics = { download: downloadCapture, downloadPcm: downloadPcmCapture, downloadManifest: downloadManifestCapture }
    console.info('[storyteller-audio] PCM capture ready; run window.__storytellerAudioDiagnostics.download() after playback to save PCM + manifest')
    worklet = null; useWorklet = canUseWorklet(audioContext)
    if (useWorklet) {
      workletReady = audioContext.audioWorklet!.addModule('/assets/pcm-ring-buffer-worklet.js').then(() => {
        if (!context.value) return
        worklet = new AudioWorkletNode(context.value, 'pcm-ring-buffer', { processorOptions: { inputSampleRate: sampleRate } })
        worklet.port.onmessage = ({ data }) => {
          if (data.type === 'state') {
            queuedSamples = data.bufferedSamples
            totalPlayedMs = (data.playedSamples / sampleRate) * 1000
            played.value = storyStartMs === null ? 0 : Math.max(0, totalPlayedMs - storyStartMs)
            buffered.value = data.bufferedSamples / sampleRate
            underruns.value = data.underruns
            if (data.underruns > reportedWorkletUnderruns) {
              reportedWorkletUnderruns = data.underruns
              console.warn('[storyteller-audio] AudioWorklet underrun', { wallClock: new Date().toISOString(), underrunCount: data.underruns, bufferedMs: Math.round(data.bufferedSamples * 1000 / sampleRate) })
            }
            if (data.expanded) console.warn('[storyteller-audio] PCM ring buffer expanded', { capacitySamples: data.capacity, capacityMs: Math.round(data.capacity * 1000 / sampleRate) })
            return
          }
          if (data.type === 'ended') { playing.value = false; paused.value = false; buffered.value = 0; return }
          if (data.type === 'underrun-start') {
            console.warn('[storyteller-audio] AudioWorklet underrun start', { wallClock: new Date().toISOString(), outputSample: data.outputSample, lastOutputSample: Number(data.lastOutputSample.toFixed(4)), bufferedMs: Math.round(data.bufferedSamples * 1000 / sampleRate) })
            return
          }
          if (data.type === 'underrun-recovery') console.warn('[storyteller-audio] AudioWorklet underrun recovery', { wallClock: new Date().toISOString(), outputSample: data.outputSample, firstRecoveredSample: Number(data.firstRecoveredSample.toFixed(4)), bufferedMs: Math.round(data.bufferedSamples * 1000 / sampleRate) })
        }
        worklet.connect(context.value.destination)
        flushPending()
      }).catch((error) => {
        worklet = null
        useWorklet = false
        console.warn('[storyteller-audio] AudioWorklet unavailable; switching to scheduled AudioBuffer playback', error)
        for (const samples of pending) scheduleFallback(samples)
        pending = []
      })
    } else {
      workletReady = null
    }
  }

  function setUnit(label: string) { unit = label; previousArrivalMs = null; if (storyStartMs === null && label.startsWith('line:')) storyStartMs = totalPlayedMs + (queuedSamples / sampleRate) * 1000 }

  function append(data: ArrayBuffer) {
    if (!context.value || data.byteLength % 2) return
    const samples = new Int16Array(data)
    if (!samples.length) return
    const firstSample = samples[0] / 32768; const lastSample = samples[samples.length - 1] / 32768
    const now = context.value.currentTime; const wallNow = performance.now()
    const arrivalGapMs = previousArrivalMs === null ? null : wallNow - previousArrivalMs
    const sampleDelta = previousLastSample === null ? null : firstSample - previousLastSample
    const unitBoundary = previousUnit !== null && previousUnit !== unit
    const bufferedBefore = queuedSamples / sampleRate
    frameCount += 1
    if (!captureTruncated && captureBytes + data.byteLength <= maxCaptureBytes) {
      const copy = new Uint8Array(data.byteLength)
      copy.set(new Uint8Array(data))
      captureParts.push(copy); captureBytes += copy.byteLength
      hasCapturedAudio.value = true
    } else if (!captureTruncated) {
      captureTruncated = true
      console.warn('[storyteller-audio] PCM capture reached 200 MB; remaining frames are not cached')
    }
    captureManifest.push({ frame: frameCount, unit, wallClock: new Date().toISOString(), bytes: data.byteLength, samples: samples.length, firstSample: Number(firstSample.toFixed(6)), lastSample: Number(lastSample.toFixed(6)) })
    console.log('[storyteller-audio] PCM frame', {
      wallClock: new Date().toISOString(), frame: frameCount, unit,
      arrivalGapMs: arrivalGapMs === null ? null : Number(arrivalGapMs.toFixed(1)),
      playbackGapMs: 0, bufferAheadMs: Number((bufferedBefore * 1000).toFixed(1)),
      firstSample: Number(firstSample.toFixed(4)), lastSample: Number(lastSample.toFixed(4)),
      sampleDelta: sampleDelta === null ? null : Number(sampleDelta.toFixed(4)), bytes: data.byteLength,
    })
    if (sampleDelta !== null && Math.abs(sampleDelta) >= 0.2) {
      console.warn('[storyteller-audio] PCM boundary candidate', {
        wallClock: new Date().toISOString(), frame: frameCount, unit,
        firstSample: Number(firstSample.toFixed(4)), previousLastSample: Number(previousLastSample!.toFixed(4)),
        sampleDelta: Number(sampleDelta.toFixed(4)), bufferAheadMs: Number((bufferedBefore * 1000).toFixed(1)),
      })
    }
    if (unitBoundary && sampleDelta !== null) {
      console.warn('[storyteller-audio] PCM unit boundary', {
        wallClock: new Date().toISOString(), frame: frameCount, fromUnit: previousUnit, toUnit: unit,
        previousLastSample: Number(previousLastSample!.toFixed(4)), firstSample: Number(firstSample.toFixed(4)),
        sampleDelta: Number(sampleDelta.toFixed(4)), playbackGapMs: 0,
        bufferAheadMs: Number((bufferedBefore * 1000).toFixed(1)),
      })
    }
    const floatSamples = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i += 1) floatSamples[i] = samples[i] / 32768
    queuedSamples += floatSamples.length
    if (worklet) worklet.port.postMessage({ type: 'write', samples: floatSamples.buffer }, [floatSamples.buffer])
    else if (useWorklet) pending.push(floatSamples)
    else scheduleFallback(floatSamples)
    buffered.value = queuedSamples / sampleRate
    previousLastSample = lastSample; previousUnit = unit; previousArrivalMs = wallNow
  }

  async function togglePause() {
    if (!context.value) return
    if (paused.value) await context.value.resume(); else await context.value.suspend()
    paused.value = !paused.value; playing.value = !paused.value
  }

  function finish() {
    if (worklet) worklet.port.postMessage({ type: 'end' })
    else if (useWorklet && workletReady) void workletReady.then(() => worklet?.port.postMessage({ type: 'end' }))
    else playing.value = false
  }

  function replay() {
    if (!captureParts.length) {
      console.warn('[storyteller-audio] No captured PCM available for replay')
      return false
    }
    const frames = captureParts.map((part, index) => ({
      data: part.slice().buffer,
      unit: String(captureManifest[index]?.unit || 'unknown'),
    }))
    begin(sampleRate)
    for (const frame of frames) {
      setUnit(frame.unit)
      append(frame.data)
    }
    finish()
    console.info('[storyteller-audio] Replaying captured PCM', { frames: frames.length, bytes: frames.reduce((sum, frame) => sum + frame.data.byteLength, 0) })
    return true
  }

  function replayDirect() {
    if (!captureParts.length) {
      console.warn('[storyteller-audio] No captured PCM available for direct replay')
      return false
    }
    const totalBytes = captureParts.reduce((sum, part) => sum + part.byteLength, 0)
    const pcm = new Int16Array(totalBytes / 2)
    let offset = 0
    for (const part of captureParts) {
      pcm.set(new Int16Array(part.buffer, part.byteOffset, part.byteLength / 2), offset)
      offset += part.byteLength / 2
    }

    worklet?.port.postMessage({ type: 'reset' }); worklet?.disconnect(); worklet = null; useWorklet = false; pending = []; workletReady = null
    void context.value?.close()
    context.value = new AudioContext()
    void context.value.resume()
    cursor.value = context.value.currentTime; paused.value = false; playing.value = true; played.value = 0; buffered.value = 0; underruns.value = 0; storyStartMs = 0; totalPlayedMs = 0
    const audio = context.value.createBuffer(1, pcm.length, sampleRate)
    const samples = audio.getChannelData(0)
    for (let i = 0; i < pcm.length; i += 1) samples[i] = pcm[i] / 32768
    const source = context.value.createBufferSource()
    source.buffer = audio; source.connect(context.value.destination)
    const at = Math.max(context.value.currentTime + 0.05, cursor.value)
    source.start(at); cursor.value = at + audio.duration; buffered.value = audio.duration
    source.onended = () => { playing.value = false; paused.value = false; buffered.value = 0 }
    console.info('[storyteller-audio] Direct continuous AudioBuffer replay', { frames: captureParts.length, samples: pcm.length, durationMs: Math.round(audio.duration * 1000) })
    return true
  }

  const captureManifest: Array<Record<string, unknown>> = []
  function captureBlobs() {
    if (!captureParts.length) { console.warn('[storyteller-audio] No PCM frames captured'); return }
    const pcm = new Blob(captureParts, { type: 'application/octet-stream' })
    const manifest = new Blob([JSON.stringify({ capturedAt: captureStartedAt, inputSampleRate: sampleRate, channels: 1, format: 's16le', bytes: captureBytes, truncated: captureTruncated, frames: captureManifest }, null, 2)], { type: 'application/json' })
    const stamp = new Date().toISOString().replace(/[:.]/g, '-')
    return { pcm, manifest, stamp }
  }
  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  function downloadPcmCapture() {
    const files = captureBlobs(); if (!files) return
    triggerDownload(files.pcm, `storyteller-audio-${files.stamp}.pcm`)
    console.info('[storyteller-audio] PCM capture downloaded', { frames: captureManifest.length, bytes: captureBytes, truncated: captureTruncated })
  }
  function downloadManifestCapture() {
    const files = captureBlobs(); if (!files) return
    triggerDownload(files.manifest, `storyteller-audio-${files.stamp}.json`)
    console.info('[storyteller-audio] PCM manifest downloaded', { frames: captureManifest.length, bytes: captureBytes, truncated: captureTruncated })
  }
  function downloadCapture() {
    const files = captureBlobs(); if (!files) return
    triggerDownload(files.pcm, `storyteller-audio-${files.stamp}.pcm`)
    window.setTimeout(() => triggerDownload(files.manifest, `storyteller-audio-${files.stamp}.json`), 1200)
    console.info('[storyteller-audio] PCM capture and manifest download requested', { frames: captureManifest.length, bytes: captureBytes, truncated: captureTruncated })
  }

  function stop() {
    worklet?.port.postMessage({ type: 'reset' }); worklet?.disconnect(); worklet = null; useWorklet = false; pending = []; queuedSamples = 0
    context.value?.close(); context.value = null; cursor.value = 0; buffered.value = 0; played.value = 0; playing.value = false; storyStartMs = null; unit = 'unknown'; previousUnit = null
  }

  return { begin, setUnit, append, togglePause, finish, replay, replayDirect, stop, paused, playing, hasCapturedAudio, bufferedMs: computed(() => Math.round(buffered.value * 1000)), playedMs: played, underruns }
}
