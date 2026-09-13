<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { PCM_SAMPLE_RATE, pcmBytesToFloat32, pcmDurationMs, splitPcmByManifest } from './audioDiagnostics'

type Mode = 'worklet' | 'native' | 'native-rate'
const modes: Array<{ id: Mode; title: string; description: string }> = [
  { id: 'worklet', title: '当前 Worklet', description: '默认 AudioContext + Ring Buffer + 当前自定义重采样' },
  { id: 'native', title: '连续 AudioBuffer', description: '单个连续节点，由浏览器原生重采样' },
  { id: 'native-rate', title: '24kHz Worklet', description: '请求 24kHz AudioContext，尽量绕过自定义重采样' },
]

const fileName = ref('')
const pcm = ref<Float32Array | null>(null)
const rawPcm = ref<ArrayBuffer | null>(null)
const manifestFrames = ref<Array<{ bytes: number }>>([])
const durationMs = ref(0)
const busy = ref(false)
const paused = ref(false)
const status = ref('请先选择一个 24kHz / mono / s16le PCM 文件')
const activeMode = ref<Mode | null>(null)
const actualRate = ref<number | null>(null)
const requestedRate = ref<number | null>(null)
const underruns = ref(0)
const error = ref('')
let context: AudioContext | null = null
let source: AudioBufferSourceNode | null = null
let worklet: AudioWorkletNode | null = null

const durationLabel = computed(() => `${(durationMs.value / 1000).toFixed(2)} 秒`)
const rateLabel = computed(() => actualRate.value ? `${actualRate.value}Hz${actualRate.value === PCM_SAMPLE_RATE ? '（原生）' : '（需要重采样）'}` : '—')
const chunkedPcm = computed(() => {
  if (!rawPcm.value || !manifestFrames.value.length) return rawPcm.value ? [rawPcm.value] : []
  try { return splitPcmByManifest(rawPcm.value, manifestFrames.value) } catch { return [rawPcm.value] }
})
const writeModeLabel = computed(() => manifestFrames.value.length && chunkedPcm.value.length > 1 ? `原始分块写入 · ${chunkedPcm.value.length} 帧` : '单次写入')

function readS16le(buffer: ArrayBuffer) {
  if (buffer.byteLength % 2 !== 0) throw new Error('PCM 文件大小不是 2 字节采样点的整数倍')
  const input = new Int16Array(buffer)
  const output = new Float32Array(input.length)
  for (let i = 0; i < input.length; i += 1) output[i] = input[i] / 32768
  return output
}

async function selectFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  stop()
  error.value = ''
  try {
    const bytes = await file.arrayBuffer()
    pcm.value = readS16le(bytes)
    rawPcm.value = bytes
    fileName.value = file.name
    durationMs.value = pcmDurationMs(bytes.byteLength)
    status.value = '文件已加载，可以分别播放三种方案'
  } catch (e) {
    pcm.value = null; fileName.value = ''; durationMs.value = 0
    error.value = e instanceof Error ? e.message : '无法读取 PCM 文件'
  }
}

async function selectManifest(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  error.value = ''
  try {
    const data = JSON.parse(await file.text())
    const frames = Array.isArray(data.frames) ? data.frames : []
    if (!frames.length) throw new Error('JSON 中没有 frames')
    manifestFrames.value = frames.map((frame: any) => ({ bytes: Number(frame.bytes) }))
    if (rawPcm.value) splitPcmByManifest(rawPcm.value, manifestFrames.value)
    status.value = `manifest 已加载 · ${manifestFrames.value.length} 个原始 frame`
  } catch (e) {
    manifestFrames.value = []
    error.value = e instanceof Error ? e.message : '无法读取 manifest JSON'
  }
}

function createContext(mode: Mode) {
  requestedRate.value = mode === 'native-rate' ? PCM_SAMPLE_RATE : null
  if (mode !== 'native-rate') return new AudioContext()
  try { return new AudioContext({ sampleRate: PCM_SAMPLE_RATE }) } catch { return new AudioContext() }
}

async function play(mode: Mode) {
  if (!pcm.value || busy.value) return
  stop()
  const samples = pcm.value
  const ctx = createContext(mode)
  context = ctx; actualRate.value = ctx.sampleRate; activeMode.value = mode; busy.value = true; paused.value = false; underruns.value = 0; error.value = ''
  await ctx.resume()
  try {
    if (mode === 'native') {
      const buffer = ctx.createBuffer(1, samples.length, PCM_SAMPLE_RATE)
      buffer.getChannelData(0).set(samples)
      source = ctx.createBufferSource(); source.buffer = buffer; source.connect(ctx.destination)
      source.onended = () => { busy.value = false; paused.value = false; status.value = '连续 AudioBuffer 播放完成' }
      source.start()
      status.value = `连续 AudioBuffer 播放中 · ${rateLabel.value}`
      return
    }
    if (!ctx.audioWorklet || typeof AudioWorkletNode === 'undefined') throw new Error('当前浏览器不支持 AudioWorklet')
    await ctx.audioWorklet.addModule('/pcm-ring-buffer-worklet.js')
    worklet = new AudioWorkletNode(ctx, 'pcm-ring-buffer', { processorOptions: { inputSampleRate: PCM_SAMPLE_RATE } })
    worklet.port.onmessage = ({ data }) => {
      if (data.type === 'state') underruns.value = data.underruns
      if (data.type === 'underrun-start') underruns.value += 1
      if (data.type === 'ended') { busy.value = false; paused.value = false; status.value = `${modes.find(item => item.id === mode)?.title} 播放完成` }
    }
    worklet.connect(ctx.destination)
    const parts = chunkedPcm.value
    for (const part of parts) {
      const transfer = pcmBytesToFloat32(part).buffer
      worklet.port.postMessage({ type: 'write', samples: transfer }, [transfer])
    }
    worklet.port.postMessage({ type: 'end' })
    status.value = `${modes.find(item => item.id === mode)?.title} 播放中 · ${rateLabel.value} · ${writeModeLabel.value}`
  } catch (e) {
    busy.value = false; error.value = e instanceof Error ? e.message : '播放失败'; status.value = '播放失败'; stop()
  }
}

async function togglePause() {
  if (!context) return
  if (paused.value) await context.resume(); else await context.suspend()
  paused.value = !paused.value
}

function stop() {
  source?.stop(); source?.disconnect(); source = null
  worklet?.port.postMessage({ type: 'reset' }); worklet?.disconnect(); worklet = null
  void context?.close(); context = null
  busy.value = false; paused.value = false; activeMode.value = null
}

onBeforeUnmount(stop)
</script>

<template>
  <section class="diagnostics-page">
    <router-link to="/" class="back">← 返回放映室</router-link>
    <p class="eyebrow">AUDIO LAB / PCM REPRODUCTION</p>
    <h1>找出那一声<br><em>不该出现的哔。</em></h1>
    <p class="diagnostics-lede">同一份 PCM、同一台设备，分别走三条播放路径。请在相同位置对比听感。</p>

    <div class="diagnostics-upload">
      <label for="pcm-file">选择 PCM 文件</label>
      <input id="pcm-file" type="file" accept=".pcm,application/octet-stream" @change="selectFile">
      <label for="manifest-file">选择配套 JSON（可选）</label>
      <input id="manifest-file" type="file" accept=".json,application/json" @change="selectManifest">
      <div v-if="pcm" class="file-meta"><b>{{ fileName }}</b><span>{{ durationLabel }} · 24kHz mono s16le</span></div>
    </div>

    <p v-if="error" class="error error-detail">{{ error }}</p>
    <div class="diagnostics-status"><span class="live-dot" :class="{on: busy}"></span>{{ status }}</div>

    <div class="diagnostics-facts">
      <span>输入 <b>24000Hz</b></span><span>实际输出 <b>{{ rateLabel }}</b></span><span>underrun <b>{{ underruns }}</b></span>
    </div>

    <div class="diagnostics-options">
      <article v-for="mode in modes" :key="mode.id" class="diagnostic-card" :class="{active: activeMode === mode.id}">
        <div><p class="card-index">0{{ modes.indexOf(mode) + 1 }}</p><h2>{{ mode.title }}</h2><p>{{ mode.description }}</p></div>
        <button class="primary" :disabled="!pcm || busy" @click="play(mode.id)">播放这一方案 ↗</button>
      </article>
    </div>
    <div class="diagnostics-actions"><button class="text-button" :disabled="!busy" @click="togglePause">{{ paused ? '继续播放' : '暂停播放' }}</button><button class="text-button" :disabled="!busy" @click="stop">停止</button></div>
    <p class="diagnostics-note">Worklet 方案会按 JSON 中的原始 frame 分块写入；连续 AudioBuffer 方案始终把整段 PCM 一次性播放，仅用于对照诊断。</p>
  </section>
</template>

<style scoped>
.diagnostics-page{max-width:1080px;margin:0 auto;padding:clamp(55px,9vw,110px) clamp(22px,6vw,80px)}
.diagnostics-page h1{font-family:'Noto Serif SC',Georgia,serif;font-size:clamp(42px,6vw,76px);line-height:1.16;letter-spacing:-.055em;margin:20px 0}.diagnostics-page h1 em{color:var(--coral);font-style:normal}.diagnostics-lede{color:#9ba9bc;max-width:520px;line-height:1.8;margin-bottom:38px}.diagnostics-upload{border:1px dashed #526782;padding:20px;background:#111d30;display:flex;align-items:center;gap:18px;flex-wrap:wrap}.diagnostics-upload label{color:var(--teal);font-size:12px}.diagnostics-upload input{color:#9ba9bc;font-size:12px;max-width:100%}.file-meta{display:flex;flex-direction:column;color:var(--paper);font-size:13px}.file-meta span{color:#8090a6;font-size:11px;margin-top:3px}.diagnostics-status{margin:22px 0;color:#b7c2d0;font-size:13px;display:flex;gap:9px;align-items:center}.diagnostics-facts{display:flex;gap:25px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:15px 0;color:#8090a6;font-size:11px}.diagnostics-facts b{color:var(--paper);font-weight:500;margin-left:5px}.diagnostics-options{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:20px}.diagnostic-card{min-height:245px;padding:22px;background:#121e31;border:1px solid #2a3b55;display:flex;flex-direction:column;justify-content:space-between;transition:border-color .2s,transform .2s}.diagnostic-card.active{border-color:var(--coral);transform:translateY(-2px)}.card-index{color:var(--coral);font-size:11px;letter-spacing:.12em;margin:0 0 25px}.diagnostic-card h2{font-family:'Noto Serif SC',Georgia,serif;color:var(--paper);font-size:22px;margin:0 0 10px}.diagnostic-card p:not(.card-index){color:#8999ad;font-size:12px;line-height:1.7;margin:0}.diagnostic-card .primary{align-self:flex-start;font-size:12px}.diagnostics-actions{display:flex;gap:18px;margin-top:18px}.diagnostics-actions button:disabled{opacity:.4;cursor:not-allowed}.diagnostics-note{color:#687a91;font-size:11px;margin-top:35px}@media(max-width:760px){.diagnostics-options{grid-template-columns:1fr}.diagnostic-card{min-height:180px}.diagnostics-facts{gap:12px;flex-wrap:wrap}}
</style>
