import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({ authenticated: false, checked: false }),
  actions: {
    async check() { try { this.authenticated = (await api.me()).authenticated } finally { this.checked = true } },
    async login(password: string) { await api.login(password); this.authenticated = true },
    async logout() { await api.logout(); this.authenticated = false },
  },
})
