<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../api'
import type { ConnectionTestPayload, SettingsPatch, SettingsResponse } from '../types'

const settings = ref<SettingsResponse | null>(null)
const error = ref('')
const notice = ref('')
const dirty = ref(false)
const saving = ref<string | null>(null)
const testing = ref<string | null>(null)
const statuses = reactive<Record<string, string>>({})
const draft = reactive<any>({ web: {}, llm: {}, tts: {}, sound: {} })

const sourceLabel = (source: string | undefined) => source === 'admin' ? '后台设置' : source === 'environment' ? '环境变量' : '程序默认值'
const sourceClass = (source: string | undefined) => `source-${source || 'default'}`
const sourceAt = (group: string, key: string) => ((settings.value?.sources as any)?.[group] as any)?.[key]
function copyDraft(value: SettingsResponse) {
  draft.web = { ...value.web, passwords: '', secret: '' }
  for (const group of ['llm', 'tts', 'sound']) copyGroupDraft(value, group)
  dirty.value = false
}

function copyGroupDraft(value: SettingsResponse, group: string) {
  const original: any = (value as any)[group]
  if (group === 'web') {
    draft.web = { ...original, passwords: '', secret: '' }
    return
  }
  draft[group] = { ...original, providers_text: (original.providers || []).join(','), provider_config: {} }
  for (const [name, config] of Object.entries(original.provider_config || {})) {
    draft[group].provider_config[name] = { ...(config as any), api_key: '' }
  }
}

async function load() {
  try { settings.value = await api.getSettings(); copyDraft(settings.value) }
  catch (err: any) { error.value = err?.message || '配置加载失败' }
}

function providerPatch(group: string) {
  const value: any = draft[group]
  const patch: any = { providers: String(value.providers_text || '').split(',').map((item: string) => item.trim()).filter(Boolean), provider_config: {} }
  if (group !== 'sound') patch.default_provider = value.default_provider
  for (const [name, config] of Object.entries(value.provider_config || {})) {
    const item: any = {}
    for (const key of ['type', 'model', 'models', 'endpoint', 'base_url', 'resource_id', 'workspace_id']) if (config && (config as any)[key] !== undefined) item[key] = (config as any)[key]
    if ((config as any)?.api_key) item.api_key = (config as any).api_key
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
    settings.value = result.settings; copyGroupDraft(result.settings, group); notice.value = `${result.message}；已对新任务生效`
  } catch (err: any) { error.value = err?.message || '配置保存失败' }
  finally { saving.value = null }
}

function testPayload(group: 'llm' | 'tts'): ConnectionTestPayload {
  const value: any = draft[group]
  const provider = value.default_provider || value.providers?.[0] || ''
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
  try { const result = await api.resetSettings(paths); settings.value = result.settings; copyGroupDraft(result.settings, group); notice.value = result.message }
  catch (err: any) { error.value = err?.message || '恢复失败' }
}

function markDirty() { dirty.value = true; notice.value = '' }
function beforeLeave(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => { if (dirty.value && !window.confirm('有未保存的配置，确定离开吗？')) return false; dirty.value = false })
onMounted(() => { window.addEventListener('beforeunload', beforeLeave); load() })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeLeave))

const groups = computed(() => settings.value ? ['llm', 'tts', 'sound'] : [])
</script>

<template>
  <section class="settings-page panel">
    <div class="section-heading"><div><p class="eyebrow">后台管理</p><h1>系统配置</h1><p>环境变量提供默认值，后台修改将对新任务生效。</p></div><span class="status-pill">单实例</span></div>
    <p v-if="error" class="error">{{error}}</p><p v-if="notice" class="settings-notice">{{notice}}</p>
    <details open class="settings-section"><summary>Web 服务 <small>配置来源：环境变量 / 后台设置</small></summary><div v-if="settings" class="settings-form"><label>登录密码<input data-testid="web-passwords" type="password" placeholder="留空保持不变" v-model="draft.web.passwords" @input="markDirty"><small>当前：{{settings.web.passwords.masked || '未配置'}}</small></label><label>Web Secret<input type="password" placeholder="留空保持不变" v-model="draft.web.secret" @input="markDirty"><small>当前：{{settings.web.secret.masked || '未配置'}}</small></label><label>会话有效期（天）<input type="number" v-model.number="draft.web.token_ttl_days" @input="markDirty"><small :class="sourceClass(sourceAt('web','token_ttl_days'))">{{sourceLabel(sourceAt('web','token_ttl_days'))}}</small></label><label>并发任务数<input data-testid="web-concurrency" type="number" v-model.number="draft.web.concurrency" @input="markDirty"><small :class="sourceClass(sourceAt('web','concurrency'))">{{sourceLabel(sourceAt('web','concurrency'))}}</small></label><label>每分钟请求限制<input type="number" v-model.number="draft.web.rate_limit_per_min" @input="markDirty"><small :class="sourceClass(sourceAt('web','rate_limit_per_min'))">{{sourceLabel(sourceAt('web','rate_limit_per_min'))}}</small></label><label>监听地址<input readonly :value="settings.web.host"><small>请通过 Docker/部署配置修改</small></label><label>端口<input readonly :value="settings.web.port"><small>请通过 Docker/部署配置修改</small></label><label>数据目录<input readonly :value="settings.data_dir"><small>请通过 Docker/数据卷配置修改</small></label><div class="settings-actions"><button data-testid="save-web" @click="save('web')">{{saving==='web'?'保存中…':'保存 Web 配置'}}</button><button class="muted" data-testid="reset-web" @click="resetGroup('web')">恢复环境变量</button></div></div></details>
    <details v-for="group in groups" :key="group" open class="settings-section"><summary>{{group==='llm'?'大模型':group==='tts'?'TTS 音色服务':'音效与高级设置'}} <small>{{(draft[group].providers||[]).join('、')}}</small></summary><div class="settings-form"><label>启用 Provider（逗号分隔）<input :data-testid="`${group}-providers`" v-model="draft[group].providers_text" @input="markDirty"></label><label v-if="group!=='sound'">默认 Provider<select v-model="draft[group].default_provider" @change="markDirty"><option v-for="name in (draft[group].providers_text||'').split(',').map((item:string)=>item.trim()).filter(Boolean)" :key="name" :value="name">{{name}}</option></select></label><label v-if="group==='sound'">启用音效<input type="checkbox" v-model="draft[group].enabled" @change="markDirty"></label><label v-if="group==='sound'">音效目录<input v-model="draft[group].dir" @input="markDirty"></label><div v-for="(config,name) in draft[group].provider_config" :key="name" class="provider-card"><h3>{{name}}</h3><label>API Key<input type="password" :data-testid="`${group}-${name}-api-key`" placeholder="留空保持不变" v-model="config.api_key" @input="markDirty"><small>当前：{{(settings as any)?.[group]?.provider_config?.[name]?.api_key?.masked || '未配置'}}</small></label><label v-if="!(group==='tts' && name==='aliyun')">模型<input v-model="config.model" @input="markDirty"></label><label v-if="group==='tts'">模型白名单（逗号分隔）<input v-model="config.models" @input="markDirty"></label><label v-if="group==='tts' && name==='aliyun'">Workspace ID<input v-model="config.workspace_id" @input="markDirty"><small>用于自动生成阿里云 HTTP 和实时 WebSocket 地址</small></label><label v-if="!(name==='volcengine' || (group==='tts' && name==='aliyun'))">Endpoint<input v-model="config.endpoint" @input="markDirty"></label><label>资源 ID<input v-model="config.resource_id" @input="markDirty"></label></div><div class="settings-actions"><button :data-testid="`save-${group}`" @click="save(group)">{{saving===group?'保存中…':'保存配置'}}</button><button v-if="group==='llm'||group==='tts'" :data-testid="`test-${group}`" class="muted" @click="testConnection(group as 'llm'|'tts')">{{testing===group?'测试中…':'测试连接'}}</button><span v-if="group==='llm'||group==='tts'" :data-testid="`status-${group}`" class="settings-status">{{statuses[group]}}</span></div></div></details>
    <p v-if="!settings" class="empty-section">正在加载配置…</p>
  </section>
</template>
