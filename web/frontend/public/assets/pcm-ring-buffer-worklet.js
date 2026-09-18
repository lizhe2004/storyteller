class PcmRingBufferProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    this.inputSampleRate = options.processorOptions?.inputSampleRate || sampleRate
    this.phaseStep = this.inputSampleRate / sampleRate
    this.capacity = Math.max(24000 * 120, 24000)
    this.buffer = new Float32Array(this.capacity)
    this.read = 0
    this.write = 0
    this.available = 0
    this.underruns = 0
    this.processCount = 0
    this.playedSamples = 0
    this.currentSample = null
    this.nextSample = null
    this.phase = 0
    this.playedSamples = 0
    this.ended = false
    this.hasReceivedData = false
    this.wasStarved = false
    this.lastOutputSample = 0
    this.port.onmessage = ({ data }) => {
      if (data.type === 'write') this.writeSamples(new Float32Array(data.samples))
      if (data.type === 'reset') this.reset()
      if (data.type === 'end') this.ended = true
    }
  }

  writeSamples(samples) {
    if (samples.length) {
      this.hasReceivedData = true
    }
    for (const sample of samples) {
      if (this.available === this.capacity) this.grow()
      this.buffer[this.write] = sample
      this.write = (this.write + 1) % this.capacity
      this.available += 1
    }
  }

  grow() {
    const next = new Float32Array(this.capacity * 2)
    for (let i = 0; i < this.available; i += 1) next[i] = this.buffer[(this.read + i) % this.capacity]
    this.buffer = next
    this.capacity = next.length
    this.read = 0
    this.write = this.available
    this.port.postMessage({ type: 'state', bufferedSamples: this.available, playedSamples: this.playedSamples, underruns: this.underruns, expanded: true, capacity: this.capacity })
  }

  reset() {
    this.read = 0
    this.write = 0
    this.available = 0
    this.currentSample = null
    this.nextSample = null
    this.phase = 0
    this.ended = false
    this.hasReceivedData = false
    this.wasStarved = false
    this.lastOutputSample = 0
  }

  readSample() {
    if (this.available === 0) return null
    const value = this.buffer[this.read]
    this.read = (this.read + 1) % this.capacity
    this.available -= 1
    return value
  }

  process(_inputs, outputs) {
    const channel = outputs[0]?.[0]
    if (!channel) return true
    let missing = 0
    const previouslyStarved = this.wasStarved
    let firstRecoveredSample = null
    for (let i = 0; i < channel.length; i += 1) {
      if (this.currentSample === null) this.currentSample = this.readSample()
      if (this.nextSample === null) this.nextSample = this.readSample()
      if (this.currentSample === null || this.nextSample === null) {
        if (this.ended && this.available === 0 && this.currentSample !== null && this.nextSample === null) {
          channel[i] = this.currentSample
          this.lastOutputSample = channel[i]
          this.currentSample = null
          continue
        }
        channel[i] = 0
        missing += 1
      } else {
        channel[i] = this.currentSample + (this.nextSample - this.currentSample) * this.phase
        if (firstRecoveredSample === null && previouslyStarved) firstRecoveredSample = channel[i]
        this.lastOutputSample = channel[i]
        this.phase += this.phaseStep
        while (this.phase >= 1) {
          this.currentSample = this.nextSample
          this.nextSample = this.readSample()
          this.phase -= 1
          if (this.nextSample === null) break
        }
      }
    }
    const starved = missing > 0 && this.hasReceivedData
    const newUnderrun = starved && !this.wasStarved
    const recovered = previouslyStarved && !starved && firstRecoveredSample !== null
    if (newUnderrun) this.underruns += 1
    this.wasStarved = starved
    this.playedSamples += channel.length
    this.processCount += 1
    if (this.processCount % 32 === 0 || newUnderrun) {
      this.port.postMessage({ type: 'state', bufferedSamples: this.available, playedSamples: this.playedSamples, underruns: this.underruns })
    }
    if (newUnderrun) this.port.postMessage({ type: 'underrun-start', outputSample: this.playedSamples, lastOutputSample: this.lastOutputSample, bufferedSamples: this.available })
    if (recovered) this.port.postMessage({ type: 'underrun-recovery', outputSample: this.playedSamples - channel.length, firstRecoveredSample, bufferedSamples: this.available })
    if (this.ended && this.available === 0 && this.currentSample === null && this.nextSample === null) {
      this.port.postMessage({ type: 'ended', playedSamples: this.playedSamples })
      this.ended = false
    }
    return true
  }
}

registerProcessor('pcm-ring-buffer', PcmRingBufferProcessor)
