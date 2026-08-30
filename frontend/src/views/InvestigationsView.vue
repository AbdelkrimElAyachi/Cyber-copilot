<script setup>
import { onMounted, computed, ref } from 'vue'
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

const deletingId = ref(null)

async function deleteInvestigation(inv) {
  if (!confirm(`Delete "${inv.title}"? This permanently removes its evidence, analysis, and actions too.`)) return
  deletingId.value = inv.id
  try {
    await store.deleteInvestigation(inv.id)
  } catch (err) {
    alert(err.message || 'Failed to delete investigation.')
  } finally {
    deletingId.value = null
  }
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
            <option value="IN_PROGRESS">Investigating</option>
            <option value="COMPLETED">Completed</option>
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

          <button
            class="btn-ghost text-xs text-surface-500 hover:text-severity-critical shrink-0"
            :disabled="deletingId === inv.id"
            title="Delete investigation"
            @click.stop="deleteInvestigation(inv)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
              <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
