<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from './stores/auth'
const auth = useAuthStore()
const navOpen = ref(false)
onMounted(() => window.addEventListener('storyteller:logout', () => { auth.authenticated = false }))
</script>
<template>
  <div class="shell">
    <header class="topbar">
      <router-link to="/" class="brand" @click="navOpen = false"><span class="brand-mark">✦</span><span>storyteller</span></router-link>
      <button v-if="auth.authenticated" class="mobile-menu-toggle" type="button" aria-controls="primary-navigation" :aria-expanded="navOpen" @click="navOpen = !navOpen">
        <span>{{ navOpen ? '收起' : '菜单' }}</span><i :class="{ open: navOpen }" aria-hidden="true"><b></b><b></b></i>
      </button>
      <nav v-if="auth.authenticated" id="primary-navigation" :class="{ 'is-open': navOpen }" aria-label="主导航">
        <router-link to="/" @click="navOpen = false">放映室</router-link>
        <router-link to="/stories" @click="navOpen = false">故事书架</router-link>
        <router-link to="/voice-analysis" @click="navOpen = false">音色分析</router-link>
        <router-link to="/voices" @click="navOpen = false">音色管理</router-link>
        <router-link to="/audio-diagnostics" @click="navOpen = false">音频实验室</router-link>
        <router-link to="/settings" @click="navOpen = false">系统配置</router-link>
        <button class="text-button" @click="navOpen = false; auth.logout()">退出</button>
      </nav>
    </header>
    <main><router-view /></main>
    <footer class="footer">把一个念头，留成一段可以重听的声音。</footer>
  </div>
</template>
