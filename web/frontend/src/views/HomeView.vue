<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { usePlayerStore } from '../stores/player'
import { useAudioTimeline } from '../composables/useAudioTimeline'

const player = usePlayerStore()
const timeline = useAudioTimeline()
const topic = ref('')
const length = ref('short')
const complexity = ref('simple')
const withSound = ref(false)
const providers = ref<{ name: string }[]>([])
const selected = ref<string[]>([])
const busy = ref(false)

onMounted(async () => {
  try {
    const opts = await api.options()
    providers.value = opts.tts_providers
    // An empty selection means "use the configured default candidate set".
    // A future provider picker can populate this for a per-story override.
    selected.value = []
  } catch {}
})

watch(() => player.phase, phase => {
  if (['completed', 'failed', 'canceled'].includes(phase)) busy.value = false
})

const knownDurationMs = computed(() => player.lines.reduce((sum, line) => sum + (player.lineDurations[line.line_id] || 0), 0))
const progressWidth = computed(() => {
  if (knownDurationMs.value > 0 && timeline.playedMs.value > 0) {
    return Math.min(100, timeline.playedMs.value / knownDurationMs.value * 100)
  }
  return player.currentIndex < 0 || !player.lines.length ? 3 : (player.currentIndex + 1) / player.lines.length * 100
})
const activeLineIndex = computed(() => {
  if (!knownDurationMs.value || !timeline.playedMs.value) return player.currentIndex
  let elapsed = 0
  for (let i = 0; i < player.lines.length; i += 1) {
    elapsed += player.lineDurations[player.lines[i].line_id] || 0
    if (timeline.playedMs.value < elapsed) return i
  }
  return player.currentIndex
})

function submit() {
  if (!topic.value.trim() || busy.value) return
  timeline.begin()
  busy.value = true
  player.start({ topic: topic.value, length: length.value, complexity: complexity.value, with_sound: withSound.value, tts_providers: selected.value }, b => timeline.append(b), e => {
    if (e.type === 'opening_audio_start') timeline.setUnit('filler:opening')
    if (e.type === 'start_notice') timeline.setUnit('filler:notice')
    if (e.type === 'line_start') timeline.setUnit(`line:${e.line_id}`)
    if (e.type === 'complete') timeline.finish()
  })
}

function stopGeneration() {
  player.cancel()
  timeline.stop()
  busy.value = false
}
</script>

<template>
  <section class="home-grid">
    <div class="intro-copy">
      <p class="eyebrow">放映室 / NEW STORY</p>
      <h1>把一个念头，<br><em>讲成一段声音。</em></h1>
      <p class="lede">输入你此刻想听的故事。我们会替你写好、选好声音，然后从第一句开始播放。</p>
      <form class="story-form" @submit.prevent="submit">
        <label for="topic">故事主题</label>
        <textarea id="topic" v-model="topic" rows="4" placeholder="比如：一只怕黑的小狐狸，在月亮下交到了朋友"></textarea>
        <div class="form-row">
          <label>长度<select v-model="length"><option value="short">短篇</option><option value="medium">中篇</option><option value="long">长篇</option></select></label>
          <label>气质<select v-model="complexity"><option value="simple">轻柔</option><option value="medium">丰富</option><option value="rich">饱满</option></select></label>
        </div>
        <label class="switch"><input v-model="withSound" type="checkbox"><span></span>加一点环境声音</label>
        <button class="primary" :disabled="!topic.trim() || busy">{{ busy ? '故事正在准备…' : '开始放映' }} <b>↗</b></button>
      </form>
    </div>

    <div class="player-panel">
      <div class="panel-head"><span class="live-dot" :class="{on: player.phase !== 'idle'}"></span><span>{{ player.phase === 'idle' ? '还没有正在播放的故事' : player.message || player.phase }}</span></div>
      <p v-if="player.error" class="error error-detail">{{ player.error }}</p>
      <div v-if="player.title || player.lines.length" class="now-playing">
        <p class="eyebrow">NOW PLAYING</p>
        <h2>{{ player.title || '正在写下标题…' }}</h2>
        <div v-if="player.characters.length" class="character-area">
          <p class="section-label">角色</p>
          <div class="character-list"><span v-for="character in player.characters" :key="character.id" class="character-chip"><b>{{ character.name }}</b><small>{{ character.voice?.name || character.voice?.voice_id || '待匹配音色' }}</small></span></div>
        </div>
        <div class="player-controls">
          <button v-if="timeline.playing || !['completed', 'failed', 'canceled'].includes(player.phase)" class="round" :aria-label="timeline.playing ? '暂停播放' : '继续播放'" :title="timeline.playing ? '暂停播放' : '继续播放'" @click="timeline.togglePause"><span aria-hidden="true">{{ timeline.playing ? 'Ⅱ' : '▶' }}</span><small>{{ timeline.playing ? '暂停' : '继续' }}</small></button>
          <div class="meter"><i :style="{width: `${progressWidth}%`}"></i></div>
          <button v-if="timeline.hasCapturedAudio" class="cancel replay" @click="timeline.replay">↻ 重播缓存</button>
          <button v-if="timeline.hasCapturedAudio" class="cancel replay" @click="timeline.replayDirect">◌ 对照重播</button>
          <button v-if="!['completed', 'failed', 'canceled'].includes(player.phase)" class="cancel" @click="stopGeneration">停止生成</button>
        </div>
        <p v-if="player.fillerText" class="host-bubble">{{ player.fillerText }}</p>
        <div class="script-lines"><p v-for="(line, i) in player.lines" :key="line.line_id" :class="{active: i === activeLineIndex}"><span>{{ String(i + 1).padStart(2, '0') }}</span><b class="speaker">{{ line.speaker }}</b><em>{{ line.text || '……' }}</em></p></div>
        <a v-if="player.finalUrl" class="download" :href="player.finalUrl" target="_blank">播放完整版 / 下载</a>
      </div>
      <div v-else class="empty-player"><div class="moon">◐</div><p>你的下一段声音<br>会在这里开始。</p></div>
    </div>
  </section>
</template>
