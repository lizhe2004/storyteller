export interface StoryLine { line_id: string; line_type: string; character_id?: string | null; speaker: string; text: string; duration_ms?: number | null }
export interface StoryCharacter { id: string; name: string; description?: string; gender?: string | null; age?: string | null; voice?: { provider: string; model?: string | null; voice_id: string; name?: string | null; gender?: string | null; age?: string[] | null; category?: string | null; description?: string | null } | null }
export interface CharactersMatchedEvent { type: 'characters_matched'; characters: StoryCharacter[] }
export interface StoryDetail { id: string; title: string; topic: string; state: string; characters: { id: string; name: string }[]; lines: StoryLine[] }
export interface ReadyAudio { encoding: string; sample_rate: number; channels: number }
export interface ModelOption { provider: string; model: string; label: string; is_default?: boolean }

/** Streamed host opening narration; a waiting-period filler, not part of `lines`. */
export interface OpeningTextDeltaEvent { type: 'opening_text_delta'; text: string }
export interface OpeningAudioStartEvent { type: 'opening_audio_start' }
export interface OpeningAudioEndEvent { type: 'opening_audio_end'; duration_ms: number }
export interface OpeningAudioAbortEvent { type: 'opening_audio_abort' }
/** Fixed host clip played after the opening and voice matching, before the first line. */
export interface StartNoticeEvent { type: 'start_notice'; text: string }
/** Incremental formal-line text. `text` may be a suffix delta or the growing full text. */
export interface LineTextDeltaEvent { type: 'line_text_delta'; line_id: string; index: number; text: string }
export interface VoiceAnalysisJob { job_id: string; status: string; phase: string; total: number; completed: number; failed: number; skipped: number; current?: number; error_message?: string; samples?: VoiceAnalysisSample[]; voice_summaries?: any[]; suggestions?: any[] }
export interface VoiceAnalysisSample { sample_id: string; voice_id: string; story_id: string; character_name?: string; text: string; audio_path: string; result?: { status?: string; normalized_result?: { observed_gender?: string; observed_age?: string; timbre?: string[]; energy?: string; speech_rate?: string; confidence?: number; evidence?: string } } | null }

export type SettingsSource = 'admin' | 'environment' | 'default'
export type SettingsSourceTree = SettingsSource | { [key: string]: SettingsSourceTree }

export interface RedactedSetting {
  configured: boolean
  masked: string | null
  count?: number
  /** Never returned by the API; accepted only to keep rendering safely defensive. */
  value?: string
}

export interface ProviderSettings {
  type?: string | null
  api_key?: RedactedSetting
  model?: string | null
  models?: string | null
  endpoint?: string | null
  base_url?: string | null
  resource_id?: string | null
  workspace_id?: string | null
}

export interface ProviderGroupSettings {
  providers: string[]
  default_provider?: string | null
  provider_config: Record<string, ProviderSettings>
}

export interface ProviderFormType {
  label: string
  fields: string[]
}

export interface ProviderGroupSchema {
  types: Record<string, ProviderFormType>
  providers: Record<string, string | null>
  custom_types: string[]
  fixed_names: string[]
}

export interface SettingsResponse {
  web: {
    passwords: RedactedSetting
    secret: RedactedSetting
    token_ttl_days: number
    host: string
    port: number
    concurrency: number
    rate_limit_per_min: number
    filler_voice?: string | null
  }
  llm: ProviderGroupSettings
  tts: ProviderGroupSettings
  sound: ProviderGroupSettings & { enabled: boolean; dir?: string | null }
  sources: Record<'web' | 'llm' | 'tts' | 'sound', SettingsSourceTree>
  config_error: string | null
  data_dir?: string | null
  provider_schemas: Record<'llm' | 'tts' | 'sound', ProviderGroupSchema>
}

export interface ProviderConfigPatch {
  type?: string
  api_key?: string
  model?: string
  models?: string
  endpoint?: string
  base_url?: string
  resource_id?: string
  workspace_id?: string
}

export interface ProviderGroupPatch {
  providers?: string[]
  default_provider?: string | null
  provider_config?: Record<string, ProviderConfigPatch>
}

export interface SettingsPatch {
  web?: {
    passwords?: string[]
    secret?: string
    token_ttl_days?: number
    concurrency?: number
    rate_limit_per_min?: number
    filler_voice?: string
  }
  llm?: ProviderGroupPatch
  tts?: ProviderGroupPatch
  sound?: ProviderGroupPatch & { enabled?: boolean; dir?: string }
}

export interface SettingsMutationResponse {
  version: string
  updated_at: string
  effective_for: 'new_jobs'
  message: string
  settings: SettingsResponse
}

export interface ConnectionTestPayload {
  provider: string
  config: ProviderConfigPatch
  timeout_seconds?: number
  voice_id?: string
}

export interface ConnectionTestResult {
  ok: boolean
  provider: string
  message: string
}
