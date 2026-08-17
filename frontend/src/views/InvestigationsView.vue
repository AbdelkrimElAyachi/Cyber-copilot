<script setup>
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useInvestigationsStore } from '../stores/investigations.js'
import SeverityBadge from '../components/common/SeverityBadge.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'

const store = useInvestigationsStore()
const router = useRouter()

onMounted(() => {
  store.fetchInvestigations()
})

const investigations = computed(() => store.filteredInvestigations)

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

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function openInvestigation(inv) {
  router.push(`/investigations/${inv.id}`)
}
</script>

<template>
  <div class="space-y-5">
    <!-- Filters -->
    <div class="card-padded">
      <div class="flex flex-wrap items-center gap-4">
        <div>
          <label class="label">Status</label>
          <select
            class="select-field w-40"
            :value="store.filters.status"
            @change="store.setFilter('status', $event.target.value)"
          >
            <option value="">All Statuses</option>
            <option value="QUEUED">Queued</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="CLOSED">Closed</option>
          </select>
        </div>

        <div>
          <label class="label">Severity</label>
          <select
            class="select-field w-40"
            :value="store.filters.severity"
            @change="store.setFilter('severity', $event.target.value)"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <div class="flex items-end">
          <button
            v-if="store.filters.status || store.filters.severity"
            class="btn-ghost text-xs"
            @click="store.clearFilters()"
          >
            Clear filters
          </button>
        </div>

        <div class="ml-auto text-sm text-surface-500">
          {{ investigations.length }} investigation{{ investigations.length !== 1 ? 's' : '' }}
        </div>
      </div>
    </div>

    <!-- Loading -->
    <LoadingSpinner v-if="store.loading" />

    <!-- Empty State -->
    <EmptyState
      v-else-if="investigations.length === 0"
      title="No investigations found"
      message="Try adjusting your filters or wait for new alerts to trigger investigations."
    />

    <!-- Investigation List -->
    <div v-else class="space-y-2">
      <div
        v-for="inv in investigations"
        :key="inv.id"
        class="card hover:bg-surface-800/60 cursor-pointer transition-colors duration-150"
        @click="openInvestigation(inv)"
      >
        <div class="p-4 flex items-start gap-4">
          <!-- Severity indicator bar -->
          <div
            class="w-1 self-stretch rounded-full shrink-0"
            :class="{
              'bg-severity-critical': inv.severity === 'critical',
              'bg-severity-high': inv.severity === 'high',
              'bg-severity-medium': inv.severity === 'medium',
              'bg-severity-low': inv.severity === 'low',
            }"
          />

          <div class="flex-1 min-w-0">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="text-sm font-medium text-surface-100 truncate">{{ inv.title }}</h3>
                <p class="text-xs text-surface-500 mt-1 line-clamp-1">{{ inv.description }}</p>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <SeverityBadge :severity="inv.severity" />
                <StatusBadge :status="inv.status" />
              </div>
            </div>

            <div class="flex items-center gap-4 mt-3 text-xs text-surface-500">
              <span>{{ formatDate(inv.created_at) }}</span>
              <span>{{ timeAgo(inv.created_at) }}</span>
              <span v-if="inv.alert_id" class="font-mono text-surface-600">{{ inv.alert_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
