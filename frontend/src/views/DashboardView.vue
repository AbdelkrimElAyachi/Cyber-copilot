<script setup>
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useInvestigationsStore } from '../stores/investigations.js'
import StatCard from '../components/common/StatCard.vue'
import SeverityBadge from '../components/common/SeverityBadge.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'

const store = useInvestigationsStore()
const router = useRouter()

onMounted(() => {
  store.fetchInvestigations()
})

const stats = computed(() => store.stats)
const recent = computed(() => store.recentInvestigations)

function timeAgo(dateStr) {
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
