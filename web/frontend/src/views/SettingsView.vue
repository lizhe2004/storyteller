<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
function syncProviderDrafts(group: string) {
  for (const name of providerNames(group)) {
    if (!draft[group].provider_config[name]) draft[group].provider_config[name] = { type: '' }
  }
}
function providerFormType(group: string, name: string) {
  const schema = settings.value?.provider_schemas[group as 'llm' | 'tts' | 'sound']
  if (!schema) return null
  if (group === 'llm' || group === 'sound') {
    return draft[group].provider_type || draft[group].provider_config[name]?.type || null
  }
  if (schema.fixed_names.includes(name)) return schema.providers[name] || null
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
  for (const [name, config] of Object.entries(original.provider_config || {})) {
    const providerSchema = value.provider_schemas[group as 'llm' | 'tts' | 'sound']
    const configuredType = (config as any).type
    const resolvedType = providerSchema.fixed_names.includes(name)
      ? providerSchema.providers[name]
      : (configuredType && providerSchema.types[configuredType]
        ? configuredType
        : providerSchema.providers[name])
    draft[group].provider_config[name] = { ...(config as any), type: resolvedType || '', api_key: '' }
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
  for (const name of names) {
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
    patch.provider_config[name] = item
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
              <label v-if="activeGroup === 'tts'">启用 Provider
                <input :data-testid="`${activeGroup}-providers`" v-model="draft[activeGroup].providers_text" @input="markDirty" @change="syncProviderDrafts(activeGroup)">
                <small :class="sourceClass(sourceAt(activeGroup, 'providers'))">可填写多个名称，以逗号分隔，用于构建音色池。</small>
              </label>
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
            <div class="settings-block-heading"><h3>服务凭据与参数</h3><p>{{ activeGroup === 'tts' ? '各语音服务分别配置，可组合音色池。' : '凭据按所选服务类型配置。' }}密钥只显示遮罩状态，不会回填。</p></div>
            <template v-for="name in providerNames(activeGroup)" :key="name">
              <article v-if="draft[activeGroup].provider_config[name]" class="provider-card" :data-testid="`provider-card-${activeGroup}-${name}`">
                <header><h4>{{ name }}</h4><span>{{ providerTypeLabel(activeGroup, name) }}</span></header>
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
                  <label v-for="field in providerFormFields(activeGroup, name)" :key="field">{{ providerFieldLabels[field] || field }}
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
                  <p v-if="!providerFormFields(activeGroup, name).length" class="provider-empty">此服务无需额外参数。</p>
                </div>
                <p v-else class="provider-empty">先选择一种后端支持的服务类型。</p>
              </article>
            </template>
            <p v-if="!providerNames(activeGroup).length" class="provider-empty">先选择一种服务类型。</p>
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
