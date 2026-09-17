import { createApp, nextTick, type App } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'
import { useAuthStore } from './stores/auth'
import AppShell from './App.vue'

const mounted: { app: App; element: HTMLElement; router: Router }[] = []

async function mountShell() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<p>home</p>' } }, { path: '/stories', component: { template: '<p>stories</p>' } }, { path: '/:pathMatch(.*)*', component: { template: '<p>other page</p>' } }],
  })
  await router.push('/')
  await router.isReady()
  const pinia = createPinia()
  const element = document.createElement('div')
  document.body.appendChild(element)
  const app = createApp(AppShell).use(pinia).use(router)
  app.mount(element)
  useAuthStore(pinia).authenticated = true
  await nextTick()
  mounted.push({ app, element, router })
  return element
}

afterEach(() => {
  for (const item of mounted.splice(0)) {
    item.app.unmount()
    item.element.remove()
  }
})

describe('primary navigation', () => {
  it('opens the compact menu and closes it after choosing a route', async () => {
    const element = await mountShell()
    const toggle = element.querySelector('[aria-controls="primary-navigation"]') as HTMLButtonElement
    const nav = element.querySelector('#primary-navigation') as HTMLElement

    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    toggle.click()
    await nextTick()
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    ;(nav.querySelector('a[href="/stories"]') as HTMLAnchorElement).click()
    await nextTick()
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(nav.classList.contains('is-open')).toBe(false)
  })
})
