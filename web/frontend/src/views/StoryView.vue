<script setup lang="ts">
import { onMounted, ref } from 'vue'; import { useRoute } from 'vue-router'; import { api } from '../api'; import type { StoryDetail } from '../types'
const route = useRoute(); const story = ref<StoryDetail | null>(null); const error = ref(''); onMounted(async () => { try { story.value = await api.story(String(route.params.ref)) } catch (e:any) { error.value = e.message } })
</script>
<template><section class="detail-page"><router-link to="/stories" class="back">← 返回故事书架</router-link><p v-if="error" class="error">{{ error }}</p><template v-if="story"><p class="eyebrow">完整故事</p><h1>{{ story.title }}</h1><p class="lede">{{ story.topic }}</p><audio controls :src="'/api/stories/' + story.id + '/audio'"></audio><article><p v-for="line in story.lines" :key="line.line_id"><span>{{ line.speaker }}</span>{{ line.text }}</p></article></template></section></template>
