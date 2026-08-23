<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { pollerApi } from '../api/system.js'

// ── State ──────────────────────────────────────────────────────────────

const status = ref(null)
const loading = ref(true)
const actionLoading = ref(false)
const error = ref(null)

// Config form
const interval = ref(60)
const lookbackHours = ref(24)

let refreshTimer = null

// ── Computed ───────────────────────────────────────────────────────────

const isRunning = computed(() => status.value?.is_running === true)

const statusLabel = computed(() => {
  if (!status.value) return 'Loading...'
  if (status.value.is_running) return 'Running'
  const s = status.value.status
  if (s === 'error') return 'Error'
  if (s === 'stopped') return 'Stopped'
  if (s === 'not_started') return 'Not Started'
  return s?.charAt(0).toUpperCase() + s?.slice(1) || 'Unknown'
})

const statusColor = computed(() => {
  if (!status.value) return 'bg-surface-600'
  if (status.value.is_running) return 'bg-severity-low animate-pulse'
  if (status.value.status === 'error') return 'bg-severity-critical'
  return 'bg-surface-500'
})

// ── Actions ────────────────────────────────────────────────────────────

const configSynced = ref(false)

async function fetchStatus() {
  try {
    status.value = await pollerApi.getStatus()
    error.value = null
    // Only sync form values on initial load — don't overwrite user edits
    if (!configSynced.value) {
      if (status.value.interval) interval.value = status.value.interval
      if (status.value.lookback_hours) lookbackHours.value = status.value.lookback_hours
      configSynced.value = true
    }
  } catch (e) {
    error.value = 'Failed to fetch poller status'
  } finally {
    loading.value = false
  }
}

async function startPoller() {
  actionLoading.value = true
  try {
    const result = await pollerApi.start({
      interval: interval.value,
      lookback_hours: lookbackHours.value,
    })
    if (result.status === 'error') {
      error.value = result.message
    } else {
      error.value = null
    }
    await fetchStatus()
  } catch (e) {
    error.value = e.message || 'Failed to start poller'
  } finally {
    actionLoading.value = false
  }
}

async function stopPoller() {
  actionLoading.value = true
  try {
    await pollerApi.stop()
    error.value = null
    await fetchStatus()
  } catch (e) {
    error.value = e.message || 'Failed to stop poller'
  } finally {
    actionLoading.value = false
  }
}

async function runOnce() {
  actionLoading.value = true
  try {
    const result = await pollerApi.runOnce({
      lookback_hours: lookbackHours.value,
    })
    error.value = null
    await fetchStatus()
    return result
  } catch (e) {
    error.value = e.message || 'Failed to run poll'
  } finally {
    actionLoading.value = false
  }
}

async function resetWatermark() {
  if (!confirm('Reset the watermark? The next poll will re-fetch all alerts within the lookback window.')) return
  actionLoading.value = true
  try {
    await pollerApi.reset()
    error.value = null
    await fetchStatus()
  } catch (e) {
    error.value = e.message || 'Failed to reset watermark'
  } finally {
    actionLoading.value = false
  }
}

const configSaved = ref(false)

async function saveConfig() {
  actionLoading.value = true
  try {
    await pollerApi.saveConfig({
      interval: interval.value,
      lookback_hours: lookbackHours.value,
    })
    error.value = null
    configSaved.value = true
    setTimeout(() => { configSaved.value = false }, 2000)
  } catch (e) {
    error.value = e.message || 'Failed to save configuration'
  } finally {
    actionLoading.value = false
  }
}

function timeAgo(dateStr) {
  if (!dateStr) return '—'
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now - date) / 1000)
  if (seconds < 60) return 'just now'
  const intervals = [
    { label: 'y', seconds: 31536000 },
    { label: 'mo', seconds: 2592000 },
    { label: 'd', seconds: 86400 },
    { label: 'h', seconds: 3600 },
    { label: 'm', seconds: 60 },
  ]
  for (const { label, seconds: s } of intervals) {
    const count = Math.floor(seconds / s)
    if (count >= 1) return `${count}${label} ago`
  }
  return 'just now'
}

// ── Lifecycle ──────────────────────────────────────────────────────────

onMounted(() => {
  fetchStatus()
  // Auto-refresh every 5 seconds
  refreshTimer = setInterval(fetchStatus, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <div class="space-y-6 max-w-4xl">
    <div>
      <h1 class="text-xl font-semibold text-surface-100">System Settings</h1>
      <p class="text-sm text-surface-500 mt-1">Manage the alert poller and system configuration.</p>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="bg-severity-critical/10 border border-severity-critical/30 rounded-lg px-4 py-3 text-sm text-severity-critical">
      {{ error }}
    </div>

    <!-- Poller Status Card -->
    <div class="card-padded">
      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-3">
          <h2 class="section-title">Alert Poller</h2>
          <div class="flex items-center gap-2 text-xs px-2.5 py-1 rounded-full"
               :class="isRunning ? 'bg-severity-low/10 text-severity-low' : 'bg-surface-800 text-surface-400'">
            <span class="w-2 h-2 rounded-full" :class="statusColor" />
            {{ statusLabel }}
          </div>
        </div>

        <!-- Main action buttons -->
        <div class="flex items-center gap-2">
          <button
            v-if="!isRunning"
            @click="startPoller"
            :disabled="actionLoading"
            class="px-4 py-2 text-sm font-medium bg-accent hover:bg-accent-light text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {{ actionLoading ? 'Starting...' : 'Start Poller' }}
          </button>
          <button
            v-else
            @click="stopPoller"
            :disabled="actionLoading"
            class="px-4 py-2 text-sm font-medium bg-severity-critical/20 hover:bg-severity-critical/30 text-severity-critical rounded-lg transition-colors disabled:opacity-50"
          >
            {{ actionLoading ? 'Stopping...' : 'Stop Poller' }}
          </button>
        </div>
      </div>

      <!-- Status detail (error message from poller) -->
      <div v-if="status?.error_message" class="mb-4 bg-severity-critical/5 border border-severity-critical/20 rounded-lg px-4 py-3 text-sm text-severity-critical">
        <span class="font-medium">Poller error:</span> {{ status.error_message }}
      </div>

      <!-- Wazuh not configured warning -->
      <div v-if="status && !status.wazuh_configured" class="mb-4 bg-severity-high/5 border border-severity-high/20 rounded-lg px-4 py-3 text-sm text-severity-high">
        Wazuh Indexer is not configured. Check your <code class="font-mono">.env</code> file.
      </div>

      <!-- Stats Grid -->
      <div v-if="status && status.status !== 'not_started'" class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div class="bg-surface-800/50 rounded-lg p-3">
          <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Last Run</p>
          <p class="text-sm font-semibold text-surface-200 mt-1">{{ timeAgo(status.last_run_at) }}</p>
        </div>
        <div class="bg-surface-800/50 rounded-lg p-3">
          <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Last Fetch</p>
          <p class="text-sm font-semibold text-surface-200 mt-1">{{ status.alerts_fetched ?? 0 }} alerts</p>
        </div>
        <div class="bg-surface-800/50 rounded-lg p-3">
          <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Total Runs</p>
          <p class="text-sm font-semibold text-surface-200 mt-1">{{ status.total_runs ?? 0 }}</p>
        </div>
        <div class="bg-surface-800/50 rounded-lg p-3">
          <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Total Created</p>
          <p class="text-sm font-semibold text-surface-200 mt-1">{{ status.total_created ?? 0 }}</p>
        </div>
      </div>

      <!-- Watermark Info -->
      <div v-if="status?.last_timestamp" class="mb-6 text-sm text-surface-400">
        <span class="font-medium text-surface-300">Watermark:</span>
        <code class="ml-2 text-xs font-mono text-surface-500 bg-surface-800 px-2 py-0.5 rounded">{{ status.last_timestamp }}</code>
      </div>
    </div>

    <!-- Configuration Card -->
    <div class="card-padded">
      <h2 class="section-title mb-4">Poller Configuration</h2>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <div>
          <label class="block text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5">
            Poll Interval (seconds)
          </label>
          <input
            v-model.number="interval"
            type="number"
            min="10"
            max="3600"
            class="w-full px-3 py-2 bg-surface-800 border border-surface-700 rounded-lg text-sm text-surface-200 focus:outline-none focus:border-accent"
          />
          <p class="text-xs text-surface-600 mt-1">How often to check for new alerts. Min: 10s.</p>
        </div>
        <div>
          <label class="block text-xs font-medium text-surface-400 uppercase tracking-wider mb-1.5">
            Initial Lookback (hours)
          </label>
          <input
            v-model.number="lookbackHours"
            type="number"
            min="1"
            max="8760"
            class="w-full px-3 py-2 bg-surface-800 border border-surface-700 rounded-lg text-sm text-surface-200 focus:outline-none focus:border-accent"
          />
          <p class="text-xs text-surface-600 mt-1">How far back to look on first run (or after reset). Max: 8760 (1 year).</p>
        </div>
      </div>

      <div class="flex items-center gap-3 mt-4">
        <button
          @click="saveConfig"
          :disabled="actionLoading"
          class="px-4 py-2 text-sm font-medium bg-accent hover:bg-accent-light text-white rounded-lg transition-colors disabled:opacity-50"
        >
          Save Configuration
        </button>
        <span v-if="configSaved" class="text-sm text-severity-low">✓ Saved</span>
        <span v-if="isRunning" class="text-xs text-surface-500 italic">
          Note: interval changes take effect after restarting the poller.
        </span>
      </div>
    </div>

    <!-- Actions Card -->
    <div class="card-padded">
      <h2 class="section-title mb-4">Actions</h2>

      <div class="flex flex-wrap gap-3">
        <button
          @click="runOnce"
          :disabled="actionLoading || isRunning"
          class="px-4 py-2 text-sm font-medium bg-surface-700 hover:bg-surface-600 text-surface-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Run Once
        </button>
        <button
          @click="resetWatermark"
          :disabled="actionLoading || isRunning"
          class="px-4 py-2 text-sm font-medium bg-surface-700 hover:bg-surface-600 text-surface-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Reset Watermark
        </button>
      </div>
      <p class="text-xs text-surface-600 mt-3">
        <strong>Run Once</strong> — trigger a single poll without starting the loop.
        <strong>Reset Watermark</strong> — clear the saved position so the next poll re-fetches everything.
      </p>
    </div>
  </div>
</template>
