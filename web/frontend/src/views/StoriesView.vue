<script setup lang="ts">
import { onMounted, ref } from 'vue'; import { api } from '../api'; const stories = ref<any[]>([]); const error = ref(''); const deleting = ref('')
onMounted(async () => { try { stories.value = (await api.stories()).stories } catch (e:any) { error.value = e.message } })
async function removeStory(story: any) {
  const title = story.title || '未命名故事'
  if (!window.confirm(`确定删除《${title}》？删除后无法恢复。`)) return
  deleting.value = story.id; error.value = ''
  try {
    await api.deleteStory(story.id)
    stories.value = stories.value.filter((item) => item.id !== story.id)
  } catch (e:any) { error.value = e.message } finally { deleting.value = '' }
}
</script>
<template><section class="list-page"><p class="eyebrow">听过的故事</p><div class="page-title"><h1>故事书架</h1><p>每一个被讲过的念头，都值得再听一次。</p></div><p v-if="error" class="error">{{ error }}</p><div v-if="!stories.length && !error" class="empty-list">书架还是空的。<router-link to="/">去写第一个故事</router-link></div><div v-for="story in stories" :key="story.id" class="story-item"><router-link :to="'/stories/' + story.id" class="story-row"><span class="story-symbol">✦</span><span><strong>{{ story.title || '未命名故事' }}</strong><small>{{ story.created_at?.slice(0, 10) }} · {{ story.state }}</small></span><b>打开</b></router-link><button class="story-delete" type="button" :disabled="deleting === story.id" @click="removeStory(story)">删除</button></div></section></template>
