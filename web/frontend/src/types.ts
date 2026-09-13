export interface StoryLine { line_id: string; line_type: string; character_id?: string | null; speaker: string; text: string; duration_ms?: number | null }
export interface StoryCharacter { id: string; name: string; description?: string; voice?: { provider: string; voice_id: string; name?: string | null } | null }
export interface StoryDetail { id: string; title: string; topic: string; state: string; characters: { id: string; name: string }[]; lines: StoryLine[] }
export interface ReadyAudio { encoding: string; sample_rate: number; channels: number }
