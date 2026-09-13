import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import LoginView from './views/LoginView.vue'
import HomeView from './views/HomeView.vue'
import StoriesView from './views/StoriesView.vue'
import StoryView from './views/StoryView.vue'
import AudioDiagnosticsView from './views/AudioDiagnosticsView.vue'

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: LoginView, meta: { public: true } },
  { path: '/', component: HomeView }, { path: '/stories', component: StoriesView },
  { path: '/stories/:ref', component: StoryView },
  { path: '/audio-diagnostics', component: AudioDiagnosticsView },
] })
router.beforeEach(async (to) => { const auth = useAuthStore(); if (!auth.checked) await auth.check(); if (!to.meta.public && !auth.authenticated) return '/login'; if (to.path === '/login' && auth.authenticated) return '/'; })
export default router
