<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../api'
import type { ConnectionTestPayload, SettingsPatch, SettingsResponse } from '../types'

const settings = ref<SettingsResponse | null>(null)
const error = ref('')
const notice = ref('')
const saving = ref<string | null>(null)
const testing = ref<string | null>(null)
const statuses = reactive<Record<string, string>>({})
const draft = reactive<any>({ web: {}, llm: {}, tts: {}, sound: {} })
const dirtyGroups = reactive(new Set<string>())
const dirty = computed(() => dirtyGroups.size > 0)

const sourceLabel = (source: string | undefined) => source === 'admin' ? '后台设置' : source === 'environment' ? '环境变量' : '程序默认值'
const sourceClass = (source: string | undefined) => `source-${source || 'default'}`
const sourceAt = (group: string, key: string) => ((settings.value?.sources as any)?.[group] as any)?.[key]
const providerSourceAt = (group: string, name: string, key: string) => (settings.value?.sources as any)?.[group]?.provider_config?.[name]?.[key]
const providerFieldLabels: Record<string, string> = {
  api_key: 'API Key', model: '模型', models: '模型白名单',
  base_url: 'Base URL', resource_id: '资源 ID', workspace_id: 'Workspace ID',
}
const providerFieldHelp: Record<string, string> = {
  base_url: '兼容 OpenAI 接口的服务地址',
  models: '用逗号分隔；留空时使用服务默认候选',
  workspace_id: '用于生成阿里云 HTTP 和实时 WebSocket 地址',
}
function providerNames(group: string) {
  if (group === 'llm' || group === 'sound') {
    const type = draft[group].provider_type
    if (!type) return []
    return [draft[group].provider_name || (type === 'openai_compatible' ? 'openai' : type)]
  }
  return String(draft[group].providers_text || '').split(',').map((name: string) => name.trim()).filter(Boolean)
}
// Cards render for every provider that is enabled, built-in (fixed names),
// or already configured — configuration is independent of enablement.
function cardNames(group: string): string[] {
  if (group !== 'tts') return providerNames(group)
  const schema = settings.value?.provider_schemas.tts
  const names = [...providerNames('tts')]
  for (const name of schema?.fixed_names || []) if (!names.includes(name)) names.push(name)
  for (const name of Object.keys(draft.tts.provider_config || {})) if (!names.includes(name)) names.push(name)
  return names
}
function providerFormType(group: string, name: string) {
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  if (!schema) return null
  if (group === 'llm' || group === 'sound') {
    return draft[group].provider_type || draft[group].provider_config[name]?.type || null
  }
  // Fixed providers (aliyun/volcengine) resolve by name even when they were
  // not enabled at load time and thus lack a schema.providers entry.
  if (schema.fixed_names.includes(name)) return schema.providers[name] || name
  const configured = draft[group].provider_config[name]?.type
  return (configured && schema.types[configured] ? configured : schema.providers[name]) || null
}
function providerFormFields(group: string, name: string) {
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  const type = providerFormType(group, name)
  return type ? schema?.types[type]?.fields || [] : []
}
function providerTypeLabel(group: string, name: string) {
  const type = providerFormType(group, name)
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  return type ? schema?.types[type]?.label || type : '服务类型待选择'
}
function providerTypeChoices(group: string, name: string) {
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  const current = providerFormType(group, name)
  return Array.from(new Set([...(current ? [current] : []), ...(schema?.custom_types || [])]))
}
function providerTypeIsFixed(group: string, name: string) {
  if (group === 'llm' || group === 'sound') {
    return providerFormType(group, name) === 'volcengine' && name === 'volcengine'
  }
  return settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']?.fixed_names.includes(name) || false
}
function singleProviderTypeChoices(group: 'llm' | 'sound') {
  const schema = settings.value?.provider_schemas[group]
  return schema ? Object.keys(schema.types) : []
}
function setSingleProviderType(group: 'llm' | 'sound', type: string) {
  draft[group].provider_type = type
  const name = type === 'openai_compatible' ? 'openai' : type
  draft[group].provider_name = name
  if (!draft[group].provider_config[name]) draft[group].provider_config[name] = { type, api_key: '' }
  else draft[group].provider_config[name].type = type
  markDirty(group)
}
function copyDraft(value: SettingsResponse) {
  draft.web = { ...value.web, passwords: '', secret: '' }
  for (const group of ['llm', 'tts', 'sound']) copyGroupDraft(value, group)
  dirtyGroups.clear()
}

function copyGroupDraft(value: SettingsResponse, group: string) {
  const original: any = (value as any)[group]
  if (group === 'web') {
    draft.web = { ...original, passwords: '', secret: '' }
    return
  }
  draft[group] = { ...original, providers_text: (original.providers || []).join(','), provider_config: {} }
  if (group === 'llm' || group === 'sound') {
    const names = original.providers || []
    const selectedName = group === 'llm' && names.includes(original.default_provider)
      ? original.default_provider
      : names[0]
    const selectedType = selectedName
      ? value.provider_schemas[group].providers[selectedName]
        || original.provider_config?.[selectedName]?.type
      : ''
    draft[group].provider_type = selectedType || ''
    draft[group].provider_name = selectedName || ''
    if (selectedName && selectedType) {
      draft[group].provider_config[selectedName] = {
        ...(original.provider_config?.[selectedName] || {}),
        type: selectedType,
        api_key: '',
      }
    }
    return
  }
  const providerSchema = value.provider_schemas[group as 'llm' | 'tts' | 'sound']
  for (const [name, config] of Object.entries(original.provider_config || {})) {
    const configuredType = (config as any).type
    const resolvedType = providerSchema.fixed_names.includes(name)
      ? providerSchema.providers[name]
      : (configuredType && providerSchema.types[configuredType]
        ? configuredType
        : providerSchema.providers[name])
    draft[group].provider_config[name] = { ...(config as any), type: resolvedType || '', api_key: '' }
  }
  // Built-in providers always get an editable card so they can be configured
  // before (or without ever) being enabled.
  for (const name of providerSchema.fixed_names) {
    if (!draft[group].provider_config[name]) {
      draft[group].provider_config[name] = { type: providerSchema.providers[name] || name, api_key: '' }
    }
  }
}

async function load() {
  try { settings.value = await api.getSettings(); copyDraft(settings.value) }
  catch (err: any) { error.value = err?.message || '配置加载失败' }
}

function providerPatch(group: string) {
  const value: any = draft[group]
  const names = providerNames(group)
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  if (group === 'llm' && names.length !== 1) throw new Error('请选择一个大模型服务类型')
  if (group === 'sound' && value.enabled && names.length !== 1) throw new Error('启用音效前，请选择一个音效服务类型')
  const patch: any = { providers: names, provider_config: {} }
  if (group === 'llm' || group === 'tts') patch.default_provider = null
  // TTS persists every configured card, including providers that are not
  // currently enabled; `providers` above stays limited to the enabled set.
  const configNames = group === 'tts' ? cardNames(group) : names
  for (const name of configNames) {
    const config = value.provider_config[name] || {}
    const type = providerFormType(group, name)
    const typeSchema = type && schema?.types[type]
    if (!typeSchema) throw new Error(`请先为 ${name} 选择服务类型`)
    const item: any = {}
    if (config.type && !schema?.fixed_names.includes(name)) item.type = config.type
    for (const key of typeSchema.fields) {
      if (key === 'api_key') {
        if (config.api_key) item.api_key = config.api_key
      } else if (config[key] !== undefined) item[key] = config[key]
    }
    // Skip untouched built-in providers that carry no values at all.
    if (Object.keys(item).length || (settings.value as any)?.[group]?.provider_config?.[name]) patch.provider_config[name] = item
  }
  if (group === 'sound') patch.enabled = value.enabled
  if (group === 'sound' && value.dir !== undefined) patch.dir = value.dir
  return patch
}

function webPatch() {
  const patch: any = { token_ttl_days: draft.web.token_ttl_days, concurrency: draft.web.concurrency, rate_limit_per_min: draft.web.rate_limit_per_min, filler_voice: draft.web.filler_voice }
  if (draft.web.passwords) patch.passwords = draft.web.passwords.split(',').map((v: string) => v.trim()).filter(Boolean)
  if (draft.web.secret) patch.secret = draft.web.secret
  return patch
}

async function save(group: string) {
  saving.value = group; notice.value = ''; error.value = ''
  try {
    const patch: SettingsPatch = group === 'web' ? { web: webPatch() } : { [group]: providerPatch(group) }
    const result = await api.patchSettings(patch)
    settings.value = result.settings; copyGroupDraft(result.settings, group); dirtyGroups.delete(group); notice.value = `${result.message}；已对新任务生效`
  } catch (err: any) { error.value = err?.message || '配置保存失败' }
  finally { saving.value = null }
}

function testPayload(group: 'llm' | 'tts'): ConnectionTestPayload {
  const value: any = draft[group]
  const provider = providerNames(group)[0] || ''
  const config = { ...(value.provider_config?.[provider] || {}) }
  if (!config.api_key) delete config.api_key
  return { provider, config }
}

async function testConnection(group: 'llm' | 'tts') {
  testing.value = group; statuses[group] = ''
  try { const result = await api.testSettings(group, testPayload(group)); statuses[group] = result.message }
  catch (err: any) { statuses[group] = err?.message || '连接测试失败' }
  finally { testing.value = null }
}

interface RemoteModel { id: string; retiring?: boolean }

const fetchingModels = ref<string | null>(null)
const modelFetchStatus = reactive<Record<string, string>>({})
const candidateFilter = reactive<Record<string, string>>({})
const remoteModels = reactive<Record<string, RemoteModel[]>>({})
const collapsedCards = reactive(new Set<string>())
const providerPickerOpen = ref(false)

// Fetch/editor state is keyed by group:name — LLM and TTS providers can
// share a name (e.g. volcengine) and must not leak lists into each other.
const stateKey = (group: string, name: string) => `${group}:${name}`

// 'llm': candidates + a default; 'multi': candidates only (voice pool
// whitelist); 'single': exactly one selected model.
function modelEditorKind(group: string, name: string): 'llm' | 'multi' | 'single' | null {
  const type = providerFormType(group, name)
  if (!type || type === 'mock') return null
  if (group === 'llm') return 'llm'
  if (group !== 'tts') return null
  return providerFormFields(group, name).includes('models') ? 'multi' : 'single'
}

function modelTargetField(group: string, name: string) {
  const fields = providerFormFields(group, name)
  if (fields.includes('models')) return 'models'
  return fields.includes('model') ? 'model' : 'resource_id'
}

// The form field the editor replaces with its listbox.
function modelEditorField(group: string, name: string) {
  return modelEditorKind(group, name) === 'llm' ? 'models' : modelTargetField(group, name)
}

function selectedModelValue(group: string, name: string): string {
  const config = draft[group].provider_config[name] || {}
  // LLM keeps its whitelist in `models` but the default lives in `model`.
  if (modelEditorKind(group, name) === 'llm') return config.model || ''
  return config[modelTargetField(group, name)] || ''
}

function candidateList(group: string, name: string): string[] {
  return String(draft[group].provider_config[name]?.models || '').split(',').map((v: string) => v.trim()).filter(Boolean)
}

function candidatePool(group: string, name: string): RemoteModel[] {
  const pool = [...(remoteModels[stateKey(group, name)] || [])]
  for (const model of candidateList(group, name)) if (!pool.some(m => m.id === model)) pool.push({ id: model })
  if (modelEditorKind(group, name) !== 'multi') {
    const current = selectedModelValue(group, name)
    if (current && !pool.some(m => m.id === current)) pool.unshift({ id: current })
  }
  return pool
}

function filteredPool(group: string, name: string): RemoteModel[] {
  const keyword = (candidateFilter[stateKey(group, name)] || '').trim().toLowerCase()
  const pool = candidatePool(group, name)
  return keyword ? pool.filter(m => m.id.toLowerCase().includes(keyword)) : pool
}

function writeCandidates(group: string, name: string, list: string[]) {
  draft[group].provider_config[name].models = list.join(', ')
  markDirty(group)
}

function isDefaultModel(group: string, name: string, model: string) {
  return modelEditorKind(group, name) === 'llm' && model === selectedModelValue(group, name)
}

function setDefaultModel(group: string, name: string, model: string) {
  const list = candidateList(group, name)
  draft[group].provider_config[name].model = model
  if (!list.includes(model)) writeCandidates(group, name, [...list, model])
  else markDirty(group)
}

function toggleCandidate(group: string, name: string, model: string) {
  if (isDefaultModel(group, name, model)) return
  const list = candidateList(group, name)
  writeCandidates(group, name, list.includes(model) ? list.filter(m => m !== model) : [...list, model])
}

function selectSingleModel(group: string, name: string, model: string) {
  draft[group].provider_config[name][modelTargetField(group, name)] = model
  markDirty(group)
}

function customCandidateKeyword(group: string, name: string): string {
  const keyword = (candidateFilter[stateKey(group, name)] || '').trim()
  return keyword && !candidatePool(group, name).some(m => m.id === keyword) ? keyword : ''
}

function addCustomCandidate(group: string, name: string) {
  const keyword = customCandidateKeyword(group, name)
  if (!keyword) return
  if (modelEditorKind(group, name) === 'single') {
    const key = stateKey(group, name)
    remoteModels[key] = [...(remoteModels[key] || []), { id: keyword }]
    selectSingleModel(group, name, keyword)
    return
  }
  const list = candidateList(group, name)
  if (!list.includes(keyword)) writeCandidates(group, name, [...list, keyword])
}

async function fetchProviderModels(group: 'llm' | 'tts', name: string) {
  const key = stateKey(group, name)
  fetchingModels.value = key; modelFetchStatus[key] = ''
  try {
    const config = { ...(draft[group].provider_config?.[name] || {}) }
    if (!config.api_key) delete config.api_key
    const result = await api.fetchModels(group, { provider: name, config })
    remoteModels[key] = result.models
    modelFetchStatus[key] = result.models.length
      ? `已拉取 ${result.models.length} 个模型`
      : '没有识别到可用模型，可直接输入添加'
  } catch (err: any) {
    modelFetchStatus[key] = err?.message || '拉取模型列表失败'
  } finally { fetchingModels.value = null }
}

// Only auto-fetch when a key is available (typed in the draft or saved).
function providerHasKey(group: string, name: string): boolean {
  if (draft[group].provider_config?.[name]?.api_key) return true
  return Boolean((settings.value as any)?.[group]?.provider_config?.[name]?.api_key?.configured)
}

function ttsProviderOptions(): { name: string; label: string }[] {
  const schema = settings.value?.provider_schemas.tts
  const names = ['aliyun', 'volcengine', 'openai', 'mock']
  for (const name of providerNames('tts')) if (!names.includes(name)) names.push(name)
  return names.map(name => {
    const type = name === 'openai' ? 'openai_compatible' : schema?.providers[name]
    return { name, label: (type && schema?.types[type]?.label) || name }
  })
}

function toggleTtsProvider(name: string) {
  const names = providerNames('tts')
  if (names.includes(name)) {
    draft.tts.providers_text = names.filter(n => n !== name).join(',')
  } else {
    if (!draft.tts.provider_config[name]) {
      const schema = settings.value?.provider_schemas.tts
      const type = schema?.fixed_names.includes(name)
        ? name
        : name === 'openai' ? 'openai_compatible' : schema?.providers[name] || ''
      draft.tts.provider_config[name] = { type, api_key: '' }
    }
    draft.tts.providers_text = [...names, name].join(',')
    if (modelEditorKind('tts', name) && providerHasKey('tts', name) && !remoteModels[stateKey('tts', name)]) fetchProviderModels('tts', name)
  }
  markDirty('tts')
}

function toggleCard(group: string, name: string) {
  const key = stateKey(group, name)
  if (collapsedCards.has(key)) collapsedCards.delete(key)
  else collapsedCards.add(key)
}

async function resetGroup(group: string) {
  if (!window.confirm('确定恢复这一组配置的环境变量值吗？')) return
  const paths: string[] = []
  const value: any = settings.value?.[group as keyof SettingsResponse]
  for (const key of Object.keys(value || {})) if (key !== 'provider_config' && key !== 'host' && key !== 'port' && !(group === 'sound' && key === 'default_provider')) paths.push(`${group}.${key}`)
  for (const name of Object.keys(value?.provider_config || {})) for (const key of ['type', 'api_key', 'model', 'models', 'endpoint', 'base_url', 'resource_id', 'workspace_id']) paths.push(`${group}.provider_config.${name}.${key}`)
  try { const result = await api.resetSettings(paths); settings.value = result.settings; copyGroupDraft(result.settings, group); dirtyGroups.delete(group); notice.value = result.message }
  catch (err: any) { error.value = err?.message || '恢复失败' }
}

function markDirty(group?: string | Event) {
  dirtyGroups.add(typeof group === 'string' ? group : activeGroup.value)
  notice.value = ''
}
function beforeLeave(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => { if (dirty.value && !window.confirm('有未保存的配置，确定离开吗？')) return false; dirtyGroups.clear() })
onMounted(() => { window.addEventListener('beforeunload', beforeLeave); load() })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeLeave))

const activeGroup = ref('web')
const settingsSections = [
  { id: 'web', title: 'Web 服务', description: '登录、安全与任务并发' },
  { id: 'llm', title: '大模型', description: '故事生成服务' },
  { id: 'tts', title: 'TTS 音色服务', description: '语音合成与音色' },
  { id: 'sound', title: '音效服务', description: '音效生成与存储' },
]
const activeSection = computed(() => settingsSections.find(section => section.id === activeGroup.value) || settingsSections[0])

// Auto-populate the LLM candidate pool from the provider when the group
// is opened; failed fetches simply leave the pool at the saved selection.
watch(activeGroup, group => {
  if (group !== 'llm' && group !== 'tts') return
  for (const name of cardNames(group)) {
    if (modelEditorKind(group, name) && providerHasKey(group, name) && !remoteModels[stateKey(group, name)]) fetchProviderModels(group as 'llm' | 'tts', name)
  }
})
</script>

<template>
  <section class="settings-page">
    <header class="settings-header">
      <div>
        <p class="settings-kicker">STORYTELLER / CONTROL ROOM</p>
        <h1>系统配置</h1>
        <p class="settings-intro">管理故事生成服务与运行参数。环境变量提供默认值，后台修改对新任务生效。</p>
      </div>
      <span class="settings-instance"><i></i> 单实例运行</span>
    </header>

    <p v-if="error" class="settings-feedback is-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="settings-feedback is-success" role="status">{{ notice }}</p>

    <div v-if="settings" class="settings-workspace">
      <nav class="settings-navigation" data-testid="settings-navigation" aria-label="配置分组">
        <p class="settings-nav-label">配置分组</p>
        <button
          v-for="section in settingsSections"
          :key="section.id"
          :data-testid="`settings-nav-${section.id}`"
          :aria-current="activeGroup === section.id ? 'page' : undefined"
          @click="activeGroup = section.id"
        >
          <span>{{ section.title }}</span>
          <small>{{ section.description }}<b v-if="dirtyGroups.has(section.id)" class="settings-nav-dirty"> · 未保存</b></small>
        </button>
        <p class="settings-nav-note">保存后仅影响新创建的任务。</p>
      </nav>

      <section class="settings-content" data-testid="settings-group-panel" :aria-labelledby="`settings-title-${activeGroup}`">
        <header class="settings-content-header">
          <div>
            <p class="settings-kicker">{{ activeSection.description }}</p>
            <h2 :id="`settings-title-${activeGroup}`">{{ activeSection.title }}</h2>
          </div>
          <span class="settings-unsaved" :class="{ visible: dirtyGroups.has(activeGroup) }"><i></i>{{ dirtyGroups.has(activeGroup) ? '有未保存的修改' : '配置已同步' }}</span>
        </header>

        <template v-if="activeGroup === 'web'">
          <section class="settings-block">
            <div class="settings-block-heading"><h3>登录与访问</h3><p>更新凭据时填写新值，留空会保留当前凭据。</p></div>
            <div class="settings-form">
              <label>登录密码
                <input data-testid="web-passwords" type="password" autocomplete="new-password" placeholder="留空保持不变" v-model="draft.web.passwords" @input="markDirty">
                <small>当前：{{ settings.web.passwords.masked || '未配置' }} · {{ sourceLabel(sourceAt('web', 'passwords')) }}</small>
              </label>
              <label>Web Secret
                <input type="password" autocomplete="new-password" placeholder="留空保持不变" v-model="draft.web.secret" @input="markDirty">
                <small>当前：{{ settings.web.secret.masked || '未配置' }} · {{ sourceLabel(sourceAt('web', 'secret')) }}</small>
              </label>
              <label>会话有效期
                <span class="settings-input-unit"><input type="number" min="1" v-model.number="draft.web.token_ttl_days" @input="markDirty"><i>天</i></span>
                <small :class="sourceClass(sourceAt('web', 'token_ttl_days'))">{{ sourceLabel(sourceAt('web', 'token_ttl_days')) }}</small>
              </label>
              <label>默认讲述音色
                <input v-model="draft.web.filler_voice" @input="markDirty">
                <small :class="sourceClass(sourceAt('web', 'filler_voice'))">填写 provider:voice_id，例如 aliyun:voice-name。{{ sourceLabel(sourceAt('web', 'filler_voice')) }}</small>
              </label>
            </div>
          </section>

          <section class="settings-block">
            <div class="settings-block-heading"><h3>任务与服务</h3><p>并发与请求限制用于控制当前实例的处理能力。</p></div>
            <div class="settings-form">
              <label>并发任务数
                <input data-testid="web-concurrency" type="number" min="1" v-model.number="draft.web.concurrency" @input="markDirty">
                <small :class="sourceClass(sourceAt('web', 'concurrency'))">{{ sourceLabel(sourceAt('web', 'concurrency')) }}</small>
              </label>
              <label>每分钟请求限制
                <input type="number" min="0" v-model.number="draft.web.rate_limit_per_min" @input="markDirty">
                <small :class="sourceClass(sourceAt('web', 'rate_limit_per_min'))">设为 0 表示不限制。{{ sourceLabel(sourceAt('web', 'rate_limit_per_min')) }}</small>
              </label>
            </div>
            <div class="settings-readonly-grid">
              <div><small>监听地址</small><strong>{{ settings.web.host }}</strong><span>请通过 Docker / 部署配置修改</span></div>
              <div><small>端口</small><strong>{{ settings.web.port }}</strong><span>请通过 Docker / 部署配置修改</span></div>
              <div><small>数据目录</small><strong>{{ settings.data_dir }}</strong><span>请通过 Docker / 数据卷配置修改</span></div>
            </div>
          </section>
        </template>

        <template v-else>
          <section class="settings-block">
            <div class="settings-block-heading"><h3>服务选择</h3><p>{{ activeGroup === 'llm' ? '配置一个故事生成模型服务。' : activeGroup === 'tts' ? '选择参与音色匹配的语音服务。' : '配置一个音效生成服务。' }}</p></div>
            <div class="settings-form settings-form-compact">
              <label v-if="activeGroup === 'llm' || activeGroup === 'sound'">服务类型
                <select :data-testid="`${activeGroup}-provider-type`" :value="draft[activeGroup].provider_type" @change="setSingleProviderType(activeGroup as 'llm' | 'sound', ($event.target as HTMLSelectElement).value)">
                  <option value="">选择服务类型</option>
                  <option v-for="type in singleProviderTypeChoices(activeGroup as 'llm' | 'sound')" :key="type" :value="type">{{ settings.provider_schemas[activeGroup as 'llm' | 'sound'].types[type].label }}</option>
                </select>
              </label>
              <div v-if="activeGroup === 'tts'" class="provider-picker">
                <span class="provider-picker-label">启用 Provider</span>
                <div class="provider-picker-dropdown">
                  <button type="button" class="settings-button secondary" data-testid="tts-provider-picker-toggle" @click="providerPickerOpen = !providerPickerOpen">
                    {{ providerNames('tts').length ? `已选 ${providerNames('tts').length} 个` : '选择 Provider' }} ▾
                  </button>
                  <div v-if="providerPickerOpen" class="provider-picker-panel" data-testid="tts-provider-picker-panel">
                    <label v-for="option in ttsProviderOptions()" :key="option.name" class="provider-picker-option">
                      <input type="checkbox" :checked="providerNames('tts').includes(option.name)" :data-testid="`tts-provider-option-${option.name}`" @change="toggleTtsProvider(option.name)">
                      <span>{{ option.label }}</span>
                    </label>
                  </div>
                </div>
                <small :class="sourceClass(sourceAt('tts', 'providers'))">勾选参与音色匹配的语音服务，可组合音色池。</small>
              </div>
              <label v-if="activeGroup === 'sound'" class="settings-checkbox">
                <input type="checkbox" v-model="draft.sound.enabled" @change="markDirty"><span>启用音效</span>
              </label>
              <label v-if="activeGroup === 'sound'">音效目录
                <input v-model="draft.sound.dir" @input="markDirty">
                <small :class="sourceClass(sourceAt('sound', 'dir'))">{{ sourceLabel(sourceAt('sound', 'dir')) }}</small>
              </label>
            </div>
          </section>

          <section class="settings-block provider-settings">
            <div class="settings-block-heading"><h3>服务凭据与参数</h3><p>{{ activeGroup === 'tts' ? '各语音服务分别配置；配置与启用相互独立，未启用也可先完成配置。' : '凭据按所选服务类型配置。' }}密钥只显示遮罩状态，不会回填。</p></div>
            <template v-for="name in cardNames(activeGroup)" :key="name">
              <article v-if="draft[activeGroup].provider_config[name]" class="provider-card" :class="{ collapsed: collapsedCards.has(`${activeGroup}:${name}`) }" :data-testid="`provider-card-${activeGroup}-${name}`">
                <header :data-testid="`provider-card-toggle-${activeGroup}-${name}`" @click="toggleCard(activeGroup, name)">
                  <h4>{{ name }}</h4><span>{{ providerTypeLabel(activeGroup, name) }}</span>
                  <span v-if="activeGroup === 'tts'" class="provider-card-state" :class="{ enabled: providerNames('tts').includes(name) }" :data-testid="`provider-card-state-tts-${name}`">{{ providerNames('tts').includes(name) ? '已启用' : '未启用' }}</span>
                  <i class="provider-card-chevron"></i>
                </header>
                <div v-show="!collapsedCards.has(`${activeGroup}:${name}`)">
                  <div v-if="activeGroup === 'tts' && !providerTypeIsFixed(activeGroup, name)" class="settings-form settings-form-compact">
                    <label>服务类型
                      <select :data-testid="`provider-type-${activeGroup}-${name}`" v-model="draft[activeGroup].provider_config[name].type" @change="markDirty">
                        <option value="">选择后端支持的类型</option>
                        <option v-for="type in providerTypeChoices(activeGroup, name)" :key="type" :value="type">{{ settings.provider_schemas[activeGroup as 'llm' | 'tts' | 'sound'].types[type].label }}</option>
                      </select>
                      <small>服务类型决定后端使用的接口和配置项。</small>
                    </label>
                  </div>
                  <div v-if="providerFormType(activeGroup, name)" class="settings-form provider-fields">
                    <template v-for="field in providerFormFields(activeGroup, name)" :key="field">
                      <div v-if="modelEditorKind(activeGroup, name) && field === modelEditorField(activeGroup, name)" class="candidate-editor">
                        <div class="candidate-editor-head">
                          <span class="candidate-editor-title">{{ modelEditorKind(activeGroup, name) === 'llm' ? '可选模型清单' : modelEditorKind(activeGroup, name) === 'multi' ? '模型白名单' : (providerFieldLabels[modelTargetField(activeGroup, name)] || '模型') }}</span>
                          <span v-if="modelEditorKind(activeGroup, name) !== 'multi'" class="candidate-current" :data-testid="`candidate-current-${activeGroup}-${name}`">{{ modelEditorKind(activeGroup, name) === 'llm' ? '默认' : '当前' }}：{{ selectedModelValue(activeGroup, name) || '未设置' }}</span>
                          <button type="button" class="settings-button secondary" :data-testid="`candidate-refresh-${activeGroup}-${name}`" :disabled="fetchingModels === `${activeGroup}:${name}`" @click="fetchProviderModels(activeGroup as 'llm' | 'tts', name)">{{ fetchingModels === `${activeGroup}:${name}` ? '拉取中…' : '刷新列表' }}</button>
                        </div>
                        <div class="candidate-listbox">
                          <div class="candidate-search">
                            <input type="search" placeholder="筛选模型，或输入自定义模型 ID" v-model="candidateFilter[`${activeGroup}:${name}`]" :data-testid="`candidate-filter-${activeGroup}-${name}`" @keyup.enter="addCustomCandidate(activeGroup, name)">
                          </div>
                          <ul class="candidate-list" :data-testid="`candidate-list-${activeGroup}-${name}`">
                            <li v-if="customCandidateKeyword(activeGroup, name)" class="candidate-add-row">
                              <button type="button" class="candidate-action" :data-testid="`candidate-add-${activeGroup}-${name}`" @click="addCustomCandidate(activeGroup, name)">添加“{{ customCandidateKeyword(activeGroup, name) }}”</button>
                            </li>
                            <li v-for="candidate in filteredPool(activeGroup, name)" :key="candidate.id">
                              <label class="candidate-check">
                                <input v-if="modelEditorKind(activeGroup, name) === 'single'" type="radio" :name="`candidate-${activeGroup}-${name}`" :checked="selectedModelValue(activeGroup, name) === candidate.id" :data-testid="`candidate-select-${activeGroup}-${name}-${candidate.id}`" @change="selectSingleModel(activeGroup, name, candidate.id)">
                                <input v-else type="checkbox" :checked="isDefaultModel(activeGroup, name, candidate.id) || candidateList(activeGroup, name).includes(candidate.id)" :disabled="isDefaultModel(activeGroup, name, candidate.id)" :data-testid="`candidate-check-${activeGroup}-${name}-${candidate.id}`" @change="toggleCandidate(activeGroup, name, candidate.id)">
                                <span class="candidate-name">{{ candidate.id }}</span>
                              </label>
                              <span v-if="candidate.retiring" class="candidate-retiring">即将下线</span>
                              <template v-if="modelEditorKind(activeGroup, name) === 'llm'">
                                <span v-if="isDefaultModel(activeGroup, name, candidate.id)" class="candidate-default">默认模型</span>
                                <button v-else type="button" class="candidate-action" :data-testid="`candidate-default-${activeGroup}-${name}-${candidate.id}`" @click="setDefaultModel(activeGroup, name, candidate.id)">设置为默认</button>
                              </template>
                            </li>
                            <li v-if="!filteredPool(activeGroup, name).length && !customCandidateKeyword(activeGroup, name)" class="candidate-empty-row">没有匹配的模型</li>
                          </ul>
                        </div>
                        <p v-if="modelFetchStatus[`${activeGroup}:${name}`]" class="model-fetch-status" :data-testid="`fetch-models-status-${activeGroup}-${name}`">{{ modelFetchStatus[`${activeGroup}:${name}`] }}</p>
                        <p v-if="!candidatePool(activeGroup, name).length" class="provider-empty">配置 API Key 后自动拉取模型列表，也可直接输入自定义模型 ID 添加。</p>
                        <small v-if="modelEditorKind(activeGroup, name) === 'llm'">勾选的模型会出现在首页"故事模型"下拉中；默认模型始终选中。列表来自服务商接口。</small>
                        <small v-else-if="modelEditorKind(activeGroup, name) === 'multi'">勾选的模型才参与音色匹配；全部取消则表示不限制。列表来自服务商接口与本地音色目录。</small>
                        <small v-else>选择语音合成使用的模型。列表来自服务商接口与本地音色目录。</small>
                      </div>
                      <label v-else-if="!(activeGroup === 'llm' && field === 'model')">{{ providerFieldLabels[field] || field }}
                        <input
                          :type="field === 'api_key' ? 'password' : field === 'base_url' ? 'url' : 'text'"
                          :autocomplete="field === 'api_key' ? 'new-password' : undefined"
                          :data-testid="field === 'api_key' ? `${activeGroup}-${name}-api-key` : `field-${activeGroup}-${name}-${field}`"
                          :placeholder="field === 'api_key' ? '留空保持不变' : undefined"
                          v-model="draft[activeGroup].provider_config[name][field]"
                          @input="markDirty"
                        >
                        <small v-if="field === 'api_key'">当前：{{ (settings as any)?.[activeGroup]?.provider_config?.[name]?.api_key?.masked || '未配置' }} · {{ sourceLabel(providerSourceAt(activeGroup, name, field)) }}</small>
                        <small v-else-if="providerFieldHelp[field]">{{ providerFieldHelp[field] }}</small>
                        <small v-else :class="sourceClass(providerSourceAt(activeGroup, name, field))">{{ sourceLabel(providerSourceAt(activeGroup, name, field)) }}</small>
                      </label>
                    </template>
                    <p v-if="!providerFormFields(activeGroup, name).length" class="provider-empty">此服务无需额外参数。</p>
                  </div>
                  <p v-else class="provider-empty">先选择一种后端支持的服务类型。</p>
                </div>
              </article>
            </template>
            <p v-if="activeGroup === 'tts' && !providerNames('tts').length" class="provider-empty">尚未启用语音服务；可在下方完成配置，保存后在上方勾选启用。</p>
            <p v-else-if="activeGroup !== 'tts' && !providerNames(activeGroup).length" class="provider-empty">先选择一种服务类型。</p>
          </section>
        </template>

        <footer class="settings-actions">
          <div class="settings-action-status" aria-live="polite">
            <template v-if="activeGroup === 'llm' || activeGroup === 'tts'">
              <span :data-testid="`status-${activeGroup}`">{{ statuses[activeGroup] }}</span>
            </template>
          </div>
          <div class="settings-action-buttons">
            <button v-if="activeGroup === 'llm' || activeGroup === 'tts'" class="settings-button secondary" :data-testid="`test-${activeGroup}`" :disabled="testing === activeGroup" @click="testConnection(activeGroup as 'llm' | 'tts')">{{ testing === activeGroup ? '测试中…' : '测试连接' }}</button>
            <button class="settings-button secondary" :data-testid="`reset-${activeGroup}`" @click="resetGroup(activeGroup)">恢复环境变量</button>
            <button class="settings-button primary" :data-testid="`save-${activeGroup}`" :disabled="saving === activeGroup" @click="save(activeGroup)">{{ saving === activeGroup ? '保存中…' : '保存配置' }}</button>
          </div>
        </footer>
      </section>
    </div>
    <p v-else class="settings-loading">正在读取配置…</p>
  </section>
</template>
