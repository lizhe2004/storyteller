<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { usePlayerStore } from '../stores/player'
import { useAudioTimeline } from '../composables/useAudioTimeline'

const player = usePlayerStore()
const timeline = useAudioTimeline()
const playbackMode = ref<'webaudio' | 'native_mp3'>('webaudio')
const nativeAudio = ref<HTMLAudioElement | null>(null)
const nativePlaying = ref(false)
const nativeNeedsTap = ref(false)
const nativeError = ref('')
const nativeCurrentMs = ref(0)
const isPlaying = computed(() => playbackMode.value === 'native_mp3' ? nativePlaying.value : timeline.playing.value)
const playedMs = computed(() => playbackMode.value === 'native_mp3' ? nativeCurrentMs.value : timeline.playedMs.value)
const hasCapturedAudio = timeline.hasCapturedAudio
const topic = ref('')
const length = ref('short')
const complexity = ref('simple')
const withSound = ref(false)
const providers = ref<{ name: string }[]>([])
const selected = ref<string[]>([])
const busy = ref(false)
const storyIdeas = [
  '一只怕黑的小狐狸，在月亮下交到了朋友',
  '深海灯塔里，最后一条鲸鱼的来信',
  '搬到新城市的孩子，发现窗台住着一颗星星',
]

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
  if (knownDurationMs.value > 0 && playedMs.value > 0) {
    return Math.min(100, playedMs.value / knownDurationMs.value * 100)
  }
  return player.currentIndex < 0 || !player.lines.length ? 3 : (player.currentIndex + 1) / player.lines.length * 100
})
const activeLineIndex = computed(() => {
  if (!knownDurationMs.value || !playedMs.value) return player.currentIndex
  let elapsed = 0
  for (let i = 0; i < player.lines.length; i += 1) {
    elapsed += player.lineDurations[player.lines[i].line_id] || 0
    if (playedMs.value < elapsed) return i
  }
  return player.currentIndex
})

function chooseStoryIdea(idea: string) {
  topic.value = idea
  document.querySelector<HTMLTextAreaElement>('#topic')?.focus()
}

function submit() {
  if (!topic.value.trim() || busy.value) return
  nativeError.value = ''; nativeNeedsTap.value = false
  if (nativeAudio.value) { nativeAudio.value.pause(); nativeAudio.value.removeAttribute('src'); nativeAudio.value.load() }
  if (playbackMode.value === 'webaudio') timeline.begin()
  else timeline.stop()
  busy.value = true
  player.start({ topic: topic.value, length: length.value, complexity: complexity.value, with_sound: withSound.value, tts_providers: selected.value, audio_mode: playbackMode.value }, b => timeline.append(b), e => {
    if (e.type === 'ready' && playbackMode.value === 'native_mp3' && nativeAudio.value) {
      nativeAudio.value.src = `/api/streaming-jobs/${encodeURIComponent(e.job_id)}/audio`
      nativeAudio.value.load()
      void nativeAudio.value.play().then(() => { nativeNeedsTap.value = false }).catch((error: unknown) => {
        nativeNeedsTap.value = true
        nativeError.value = '浏览器拦截了自动播放，请点击“开始原生播放”。'
        console.info('[storyteller-audio] Native audio autoplay requires a user gesture', error)
      })
    }
    if (e.type === 'opening_audio_start') timeline.setUnit('filler:opening')
    if (e.type === 'start_notice') timeline.setUnit('filler:notice')
    if (e.type === 'line_start') timeline.setUnit(`line:${e.line_id}`)
    if (e.type === 'complete') timeline.finish()
  })
}

function stopGeneration() {
  player.cancel()
  nativeAudio.value?.pause()
  nativeAudio.value?.removeAttribute('src')
  nativeAudio.value?.load()
  nativePlaying.value = false
  nativeNeedsTap.value = false
  timeline.stop()
  busy.value = false
}

function togglePlayback() {
  if (playbackMode.value !== 'native_mp3' || !nativeAudio.value) {
    void timeline.togglePause()
    return
  }
  if (nativeAudio.value.paused) {
    void nativeAudio.value.play().then(() => { nativeNeedsTap.value = false }).catch(() => {
      nativeNeedsTap.value = true
      nativeError.value = '无法开始播放，请重新点击播放按钮。'
    })
  } else nativeAudio.value.pause()
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
        <label>播放方式<select v-model="playbackMode" aria-label="播放方式" :disabled="busy"><option value="webaudio">Web Audio（当前）</option><option value="native_mp3">原生 audio（MP3 实验）</option></select></label>
        <p class="playback-hint">原生 audio 用于测试息屏/后台播放；若浏览器拦截自动播放，请在播放器中手动开始。</p>
        <label class="switch"><input v-model="withSound" type="checkbox"><span></span>加一点环境声音</label>
        <button class="primary" :disabled="!topic.trim() || busy">{{ busy ? '故事正在准备…' : '开始放映' }} <b>↗</b></button>
      </form>
    </div>

    <div class="player-panel">
      <audio ref="nativeAudio" preload="none" @playing="nativePlaying = true" @pause="nativePlaying = false" @timeupdate="nativeCurrentMs = ($event.target as HTMLAudioElement).currentTime * 1000" @ended="nativePlaying = false" @error="nativeError = '原生 MP3 流播放失败，请查看服务端日志或切回 Web Audio。'" />
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
          <button v-if="isPlaying || !['completed', 'failed', 'canceled'].includes(player.phase)" class="round" :class="{ 'is-playing': isPlaying }" :aria-pressed="isPlaying" :aria-label="isPlaying ? '暂停播放' : '继续播放'" :title="isPlaying ? '暂停播放' : '继续播放'" @click="togglePlayback"><span aria-hidden="true">{{ isPlaying ? 'Ⅱ' : '▶' }}</span><small>{{ isPlaying ? '暂停' : (nativeNeedsTap ? '开始原生播放' : '继续') }}</small></button>
          <div class="meter"><i :style="{width: `${progressWidth}%`}"></i></div>
          <button v-if="hasCapturedAudio" class="cancel replay" @click="timeline.replay">↻ 重播缓存</button>
          <button v-if="hasCapturedAudio" class="cancel replay" @click="timeline.replayDirect">◌ 对照重播</button>
          <button v-if="!['completed', 'failed', 'canceled'].includes(player.phase)" class="cancel" @click="stopGeneration">停止生成</button>
        </div>
        <p v-if="nativeError" class="error error-detail">{{ nativeError }}</p>
        <p v-if="player.fillerText" class="host-bubble">{{ player.fillerText }}</p>
        <div class="script-lines"><p v-for="(line, i) in player.lines" :key="line.line_id" :class="{active: i === activeLineIndex}"><span>{{ String(i + 1).padStart(2, '0') }}</span><b class="speaker">{{ line.speaker }}</b><em>{{ line.text || '……' }}</em></p></div>
        <a v-if="player.finalUrl" class="download" :href="player.finalUrl" target="_blank">播放完整版 / 下载</a>
      </div>
      <div v-else class="empty-player">
        <div class="moon" aria-hidden="true">◐</div>
        <p>从一个小小的念头开始，<br>故事就会在这里响起。</p>
        <div class="story-ideas" role="group" aria-label="试试这些故事主题">
          <span>或者试试</span>
          <button v-for="idea in storyIdeas" :key="idea" data-testid="story-idea" type="button" @click="chooseStoryIdea(idea)">{{ idea }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
