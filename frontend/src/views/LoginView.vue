<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')

async function onSubmit() {
  if (!username.value || !password.value) return
  const ok = await auth.login(username.value, password.value)
  if (ok) {
    router.push(route.query.redirect || '/')
  }
}
</script>

<template>
  <div class="min-h-screen bg-surface-950 flex items-center justify-center px-4">
    <div class="w-full max-w-sm">
      <div class="flex flex-col items-center mb-8">
        <div class="w-12 h-12 rounded-lg bg-accent/20 flex items-center justify-center mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6 text-accent">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
        </div>
        <span class="text-base font-semibold text-surface-100 tracking-wide">CyberCopilot</span>
        <span class="text-xs font-medium text-surface-500 uppercase tracking-widest">Investigation Platform</span>
      </div>

      <form class="card-padded space-y-4" @submit.prevent="onSubmit">
        <div>
          <h1 class="text-sm font-semibold text-surface-100 mb-1">Sign in</h1>
          <p class="text-xs text-surface-500">Use your Wazuh username and password.</p>
        </div>

        <div>
          <label class="label" for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            autofocus
            class="input-field"
            placeholder="admin"
          />
        </div>

        <div>
          <label class="label" for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            class="input-field"
            placeholder="••••••••"
          />
        </div>

        <p v-if="auth.error" class="text-sm text-red-400">{{ auth.error }}</p>

        <button
          type="submit"
          class="btn-primary w-full"
          :disabled="auth.loading || !username || !password"
        >
          <span v-if="auth.loading">Signing in…</span>
          <span v-else>Sign in</span>
        </button>
      </form>
    </div>
  </div>
</template>
