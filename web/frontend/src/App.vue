<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
const auth = useAuthStore()
onMounted(() => window.addEventListener('storyteller:logout', () => { auth.authenticated = false }))
</script>
<template>
  <div class="shell">
  <header class="topbar"><router-link to="/" class="brand"><span class="brand-mark">✦</span><span>storyteller</span></router-link><nav v-if="auth.authenticated"><router-link to="/">放映室</router-link><router-link to="/stories">故事书架</router-link><router-link to="/voice-analysis">音色分析</router-link><router-link to="/audio-diagnostics">音频实验室</router-link><router-link to="/settings">系统配置</router-link><button class="text-button" @click="auth.logout">退出</button></nav></header>
    <main><router-view /></main>
    <footer class="footer">把一个念头，留成一段可以重听的声音。</footer>
  </div>
</template>
