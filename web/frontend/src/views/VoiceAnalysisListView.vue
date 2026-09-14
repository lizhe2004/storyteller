<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'; import { api } from '../api'; import type { VoiceAnalysisJob } from '../types'
const jobs=ref<VoiceAnalysisJob[]>([]); const error=ref(''); let timer:number|undefined
async function refresh(){try{jobs.value=(await api.voiceAnalysisJobs()).jobs}catch(e:any){error.value=e.message}}
async function create(){await api.createVoiceAnalysisJob({sample_limit:10}); await refresh()}
onMounted(async()=>{await refresh(); timer=window.setInterval(refresh,3000)}); onUnmounted(()=>timer&&clearInterval(timer))
</script>
<template><section class="list-page"><p class="eyebrow">后台任务</p><div class="page-title"><h1>音色分析</h1><p>分析历史 TTS 音频，发现音色库可以改进的地方。</p><button class="primary-button" @click="create">新建分析任务</button></div><p v-if="error" class="error">{{error}}</p><router-link v-for="job in jobs" :key="job.job_id" :to="'/voice-analysis/'+job.job_id" class="story-row"><span class="story-symbol">◌</span><span><strong>{{job.job_id}}</strong><small>{{job.phase}} · {{job.completed}} / {{job.total || '待扫描'}} · 失败 {{job.failed}}</small></span><b>{{job.status}}</b></router-link><div v-if="!jobs.length&&!error" class="empty-list">还没有分析任务。</div></section></template>
