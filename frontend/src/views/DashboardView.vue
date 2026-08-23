<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useInvestigationsStore } from '../stores/investigations.js'
import { pollerApi } from '../api/system.js'
import StatCard from '../components/common/StatCard.vue'
import SeverityBadge from '../components/common/SeverityBadge.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'

const store = useInvestigationsStore()
const router = useRouter()

const pollerStatus = ref(null)

onMounted(async () => {
  store.fetchInvestigations()
  pollerStatus.value = await pollerApi.getStatus()
})

const stats = computed(() => store.stats)
const recent = computed(() => store.recentInvestigations)

const pollerState = computed(() => {
  const p = pollerStatus.value
  if (!p) return null
  return {
    status: p.status || 'unknown',
    lastRun: p.last_run_at,
    lastTimestamp: p.last_timestamp,
    alertsFetched: p.alerts_fetched ?? 0,
    created: p.investigations_created ?? 0,
    totalRuns: p.total_runs ?? 0,
    totalCreated: p.total_created ?? 0,
    error: p.error_message,
    notStarted: p.status === 'not_started',
  }
})

const pollerStatusColor = computed(() => {
  if (!pollerState.value) return 'bg-surface-600'
  const s = pollerState.value.status
  if (s === 'running') return 'bg-severity-low animate-pulse'
  if (s === 'error') return 'bg-severity-critical'
  if (s === 'idle') return 'bg-severity-low'
  return 'bg-surface-600'
})

function timeAgo(dateStr) {
  if (!dateStr) return '—'
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now - date) / 1000)
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

function openInvestigation(row) {
  router.push(`/investigations/${row.id}`)
}
</script>

<template>
  <div class="space-y-6">
    <LoadingSpinner v-if="store.loading" />

    <template v-else>
      <!-- Status Overview -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Investigations" :value="stats.total" color="accent" />
        <StatCard title="Active" :value="stats.investigating" subtitle="Currently investigating" color="investigating" />
        <StatCard title="Queued" :value="stats.queued" subtitle="Awaiting investigation" color="queued" />
        <StatCard title="Closed" :value="stats.closed" subtitle="Resolved" color="closed" />
      </div>

      <!-- Severity Breakdown -->
      <div>
        <h2 class="section-title mb-3">Severity Overview</h2>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Critical" :value="stats.critical" color="critical" />
          <StatCard title="High" :value="stats.high" color="high" />
          <StatCard title="Medium" :value="stats.medium" color="medium" />
          <StatCard title="Low" :value="stats.low" color="low" />
        </div>
      </div>

      <!-- Alert Poller Status -->
      <div class="card-padded">
        <div class="flex items-center justify-between mb-3">
          <h2 class="section-title">Alert Poller</h2>
          <div v-if="pollerState" class="flex items-center gap-2 text-xs text-surface-400">
            <span class="w-2 h-2 rounded-full" :class="pollerStatusColor" />
            {{ pollerState.status }}
          </div>
        </div>

        <div v-if="!pollerState || pollerState.notStarted" class="text-sm text-surface-500">
          <p>Poller has not been started yet. Run it to pull alerts from Wazuh:</p>
          <code class="block mt-2 px-3 py-2 bg-surface-950 rounded text-xs font-mono text-surface-400">
            python poll_alerts.py --loop
          </code>
        </div>

        <div v-else-if="pollerState.error" class="text-sm">
          <p class="text-severity-critical">{{ pollerState.error }}</p>
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Last Run</p>
            <p class="text-sm text-surface-200 mt-1">{{ timeAgo(pollerState.lastRun) }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Last Fetch</p>
            <p class="text-sm text-surface-200 mt-1">{{ pollerState.alertsFetched }} alerts</p>
          </div>
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Total Runs</p>
            <p class="text-sm text-surface-200 mt-1">{{ pollerState.totalRuns }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Total Created</p>
            <p class="text-sm text-surface-200 mt-1">{{ pollerState.totalCreated }} investigations</p>
          </div>
        </div>
      </div>

      <!-- Recent Investigations -->
      <div class="card">
        <div class="flex items-center justify-between p-5 border-b border-surface-800">
          <h2 class="section-title">Recent Investigations</h2>
          <router-link to="/investigations" class="text-sm text-accent hover:text-accent-light transition-colors">
            View all &rarr;
          </router-link>
        </div>

        <div v-if="recent.length === 0" class="p-8 text-center text-surface-500 text-sm">
          No investigations yet.
        </div>

        <div v-else class="divide-y divide-surface-800">
          <div
            v-for="inv in recent"
            :key="inv.id"
            class="flex items-center gap-4 px-5 py-4 hover:bg-surface-800/50 cursor-pointer transition-colors"
            @click="openInvestigation(inv)"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-surface-200 truncate">{{ inv.title }}</p>
              <p class="text-xs text-surface-500 mt-0.5">{{ timeAgo(inv.created_at) }}</p>
            </div>
            <SeverityBadge :severity="inv.severity" />
            <StatusBadge :status="inv.status" />
          </div>
        </div>
      </div>

      <!-- Activity overview -->
      <div class="card-padded">
        <h2 class="section-title mb-3">Activity</h2>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Open Cases</p>
            <p class="text-xl font-bold text-surface-100 mt-1">{{ stats.investigating + stats.queued }}</p>
            <div class="mt-2 h-1.5 bg-surface-800 rounded-full overflow-hidden">
              <div
                class="h-full bg-accent rounded-full transition-all duration-500"
                :style="{ width: stats.total ? ((stats.investigating + stats.queued) / stats.total * 100) + '%' : '0%' }"
              />
            </div>
          </div>
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Critical + High</p>
            <p class="text-xl font-bold text-severity-high mt-1">{{ stats.critical + stats.high }}</p>
            <div class="mt-2 h-1.5 bg-surface-800 rounded-full overflow-hidden">
              <div
                class="h-full bg-severity-high rounded-full transition-all duration-500"
                :style="{ width: stats.total ? ((stats.critical + stats.high) / stats.total * 100) + '%' : '0%' }"
              />
            </div>
          </div>
          <div>
            <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">Resolution Rate</p>
            <p class="text-xl font-bold text-severity-low mt-1">
              {{ stats.total ? Math.round(stats.closed / stats.total * 100) : 0 }}%
            </p>
            <div class="mt-2 h-1.5 bg-surface-800 rounded-full overflow-hidden">
              <div
                class="h-full bg-severity-low rounded-full transition-all duration-500"
                :style="{ width: stats.total ? (stats.closed / stats.total * 100) + '%' : '0%' }"
              />
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
