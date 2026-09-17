import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({ authenticated: false, checked: false, setupRequired: false, setupAvailable: false }),
  actions: {
    async check() { try { const status = await api.authStatus(); this.setupRequired = status.setup_required; this.setupAvailable = status.setup_available; this.authenticated = (await api.me()).authenticated } finally { this.checked = true } },
    async login(password: string) { await api.login(password); this.authenticated = true },
    async setup(code: string, password: string) { await api.setup(code, password); this.authenticated = true; this.setupRequired = false; this.setupAvailable = false },
    async logout() { await api.logout(); this.authenticated = false },
  },
})
