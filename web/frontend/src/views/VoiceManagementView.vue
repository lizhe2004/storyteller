<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import type { ManagedVoice, VoiceClip, VoiceListFilters } from '../types'

const ages = ['child', 'teen', 'young_adult', 'middle_aged', 'senior']
const ageLabels: Record<string, string> = { child: '儿童', teen: '少年', young_adult: '青年', middle_aged: '中年', senior: '老年' }
const genderLabels: Record<string, string> = { female: '女', male: '男' }
const voices = ref<ManagedVoice[]>([])
const filterOptions = ref<VoiceListFilters>({ providers: [], models: [], genders: [], ages: [] })
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const filters = reactive({ provider: '', model: '', gender: '', age: '' })
const editing = reactive<Record<string, string[]>>({})
const saving = ref('')
const expanded = ref('')
const clips = reactive<Record<string, VoiceClip[]>>({})

const providers = computed(() => filterOptions.value.providers)
const models = computed(() => filterOptions.value.models)
const genders = computed(() => filterOptions.value.genders)
const pages = computed(() => Math.max(1, Math.ceil(total.value / 50)))

function labelAge(age: string) { return ageLabels[age] || age }
function labelGender(gender?: string | null) { return genderLabels[gender || ''] || gender || '未标注' }
function filtersPayload() { return { ...filters, page: page.value, page_size: 50 } }

async function load(reset = false) {
  if (reset) page.value = 1
  loading.value = true; error.value = ''
  try {
    const result = await api.voices(filtersPayload())
    voices.value = result.voices; total.value = result.total; filterOptions.value = result.filters
    result.voices.forEach(voice => { editing[voice.key] = [...voice.age] })
  } catch (err) { error.value = err instanceof Error ? err.message : '音色加载失败' }
  finally { loading.value = false }
}

async function toggleClips(voice: ManagedVoice) {
  if (expanded.value === voice.key) { expanded.value = ''; return }
  expanded.value = voice.key
  if (!clips[voice.key]) {
    try { clips[voice.key] = (await api.voiceClips(voice.key)).clips } catch (err) { error.value = err instanceof Error ? err.message : '片段加载失败' }
  }
}

async function saveAge(voice: ManagedVoice) {
  saving.value = voice.key; error.value = ''
  try {
    const updated = await api.updateVoiceAge(voice.key, editing[voice.key] || [])
    voice.age = [...updated.age]
  } catch (err) {
    editing[voice.key] = [...voice.age]
    error.value = err instanceof Error ? err.message : '年龄保存失败'
  }
  finally { saving.value = '' }
}

function audioUrl(voice: ManagedVoice, clip: VoiceClip) { return `/api/voices/${encodeURIComponent(voice.key)}/clips/${encodeURIComponent(clip.clip_id)}/audio` }
function formatDate(value: string) { return value ? new Date(value).toLocaleString() : '未知时间' }

onMounted(() => load())
</script>

<template>
  <section class="voice-management-page">
    <header class="page-title">
      <div><p class="eyebrow">VOICE LIBRARY</p><h1>音色管理</h1><p class="page-intro">查看音色、试听故事生成片段，并维护适用年龄。</p></div>
      <span class="voice-total">{{ total }} 个音色</span>
    </header>

    <div class="voice-filters" aria-label="音色筛选">
      <label>Provider<select data-testid="filter-provider" v-model="filters.provider" @change="load(true)"><option value="">全部</option><option v-for="item in providers" :key="item" :value="item">{{ item }}</option></select></label>
      <label>模型<select v-model="filters.model" @change="load(true)"><option value="">全部</option><option v-for="item in models" :key="item" :value="item">{{ item }}</option></select></label>
      <label>性别<select v-model="filters.gender" @change="load(true)"><option value="">全部</option><option v-for="item in genders" :key="item" :value="item">{{ labelGender(item) }}</option></select></label>
      <label>年龄<select v-model="filters.age" @change="load(true)"><option value="">全部</option><option v-for="item in filterOptions.ages" :key="item" :value="item">{{ labelAge(item) }}</option></select></label>
    </div>

    <p v-if="error" class="voice-error">{{ error }}</p>
    <p v-if="loading" class="voice-empty">正在加载音色…</p>
    <p v-else-if="!voices.length" class="voice-empty">没有符合筛选条件的音色。</p>
    <div v-else class="voice-table">
      <article v-for="voice in voices" :key="voice.key" data-testid="voice-row" class="voice-row">
        <div class="voice-main"><strong>{{ voice.name || voice.voice_id }}</strong><span>{{ voice.provider }} · {{ voice.model || '默认模型' }}</span><small>{{ voice.voice_id }} · {{ labelGender(voice.gender) }}</small><div class="voice-meta"><b>{{ voice.category || '未分类' }}</b><em v-for="tag in voice.tags" :key="tag">{{ tag }}</em></div><p class="voice-description">{{ voice.description || '暂无描述' }}</p></div>
        <div class="voice-age"><span>适用年龄</span><div class="age-checks"><label v-for="age in ages" :key="age"><input v-model="editing[voice.key]" type="checkbox" :value="age">{{ labelAge(age) }}</label></div><button class="small-action" :disabled="saving === voice.key" @click="saveAge(voice)">{{ saving === voice.key ? '保存中' : '保存' }}</button></div>
        <div class="voice-actions"><button class="small-action" @click="toggleClips(voice)">{{ expanded === voice.key ? '收起片段' : `试听片段（${voice.clip_count}）` }}</button></div>
        <div v-if="expanded === voice.key" class="voice-clips"><p v-if="!clips[voice.key]?.length" class="clip-empty">暂无故事生成片段。</p><div v-for="clip in clips[voice.key] || []" :key="clip.clip_id" class="clip-row"><div><strong>{{ clip.story_title }} · {{ clip.character_name }}</strong><p>{{ clip.text }}</p><small>{{ formatDate(clip.created_at) }}</small></div><audio controls preload="none" :src="audioUrl(voice, clip)"></audio></div></div>
      </article>
    </div>
    <nav v-if="pages > 1" class="voice-pagination"><button :disabled="page <= 1" @click="page--; load()">上一页</button><span>{{ page }} / {{ pages }}</span><button :disabled="page >= pages" @click="page++; load()">下一页</button></nav>
  </section>
</template>

<style scoped>
.voice-management-page{max-width:1180px;margin:0 auto;padding:64px clamp(20px,5vw,72px) 100px}.page-title{align-items:flex-end}.page-intro{margin:12px 0 0;color:#9ba9bc;font-size:13px}.voice-total{color:var(--teal);font-size:12px;white-space:nowrap}.voice-filters{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0 20px;padding:16px;border:1px solid #30445f;background:#121e31}.voice-filters label{color:#9ba9bc;font-size:11px}.voice-filters select{display:block;width:100%;margin-top:7px;padding:9px 10px;border:1px solid #38506b;border-radius:4px;background:#17263b;color:var(--paper);font-size:12px}.voice-table{border-top:1px solid var(--line)}.voice-row{display:grid;grid-template-columns:1.1fr 1.5fr auto;gap:24px;align-items:center;padding:20px 0;border-bottom:1px solid #25374f}.voice-main strong,.voice-main span,.voice-main small{display:block}.voice-main strong{color:var(--paper);font-family:'Noto Serif SC',Georgia,serif;font-size:17px}.voice-main span{margin-top:6px;color:var(--teal);font-size:11px}.voice-main small{margin-top:4px;color:#71839a;font-size:10px}.voice-meta{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}.voice-meta b,.voice-meta em{padding:3px 6px;border-radius:3px;font-size:10px;font-style:normal}.voice-meta b{background:#23414a;color:#a8ddd3;font-weight:500}.voice-meta em{background:#26354a;color:#aab9c8}.voice-description{margin:8px 0 0;color:#8799ae;font-size:11px;line-height:1.5}.voice-age>span{display:block;margin-bottom:8px;color:#8495aa;font-size:10px}.age-checks{display:flex;flex-wrap:wrap;gap:9px}.age-checks label{color:#c3cfdb;font-size:11px;white-space:nowrap}.age-checks input{accent-color:var(--teal);margin-right:4px}.small-action{padding:7px 10px;border:1px solid #386c73;border-radius:4px;background:transparent;color:var(--teal);font-size:11px}.small-action:hover:not(:disabled){background:#183b43}.small-action:disabled{opacity:.5}.voice-age .small-action{margin-top:10px}.voice-actions{align-self:start}.voice-clips{grid-column:1 / -1;padding:15px 0 0 20px;border-top:1px solid #263b55}.clip-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 0;border-bottom:1px solid #22344c}.clip-row strong{color:#d8e1e8;font-size:12px}.clip-row p{margin:5px 0;color:#9ba9bc;font-size:12px}.clip-row small{color:#6f8198;font-size:10px}.clip-row audio{width:280px;height:32px}.voice-empty,.clip-empty{color:#8495aa;font-size:13px;padding:28px 0}.voice-error{padding:11px 14px;border-left:2px solid var(--coral);background:#3a2430;color:#f3b0a0;font-size:12px}.voice-pagination{display:flex;align-items:center;justify-content:center;gap:15px;margin-top:25px;color:#9ba9bc;font-size:12px}.voice-pagination button{padding:6px 10px;border:1px solid #38506b;border-radius:4px;background:transparent;color:var(--teal)}.voice-pagination button:disabled{opacity:.4}
@media(max-width:800px){.voice-filters{grid-template-columns:1fr 1fr}.voice-row{grid-template-columns:1fr;gap:15px}.voice-actions{align-self:auto}.clip-row{align-items:flex-start;flex-direction:column}.clip-row audio{width:100%}}
@media(max-width:500px){.voice-management-page{padding:40px 16px 70px}.voice-filters{grid-template-columns:1fr}.page-title{align-items:flex-start;flex-direction:column;gap:12px}}
</style>
