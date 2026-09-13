<script setup lang="ts">
import { ref } from 'vue'; import { useRouter } from 'vue-router'; import { useAuthStore } from '../stores/auth'
const password = ref(''); const error = ref(''); const busy = ref(false); const auth = useAuthStore(); const router = useRouter()
async function submit() { busy.value = true; error.value = ''; try { await auth.login(password.value); router.push('/') } catch { error.value = '密码不正确，或者服务还没有准备好。' } finally { busy.value = false } }
</script>
<template><section class="login-page"><div class="login-orbit">✦</div><p class="eyebrow">你的私人放映室</p><h1>今晚，听一个<br><em>只属于你的故事。</em></h1><form @submit.prevent="submit"><label for="password">访问密码</label><input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="输入密码" autofocus><p v-if="error" class="error">{{ error }}</p><button class="primary wide" :disabled="busy">{{ busy ? '正在进入…' : '进入放映室' }}</button></form></section></template>
