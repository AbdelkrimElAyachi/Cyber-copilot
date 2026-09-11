<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInvestigationsStore } from '../stores/investigations.js'
import SeverityBadge from '../components/common/SeverityBadge.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'
import { renderMarkdown } from '../utils/markdown.js'

const route = useRoute()
const router = useRouter()
const store = useInvestigationsStore()

const activeTab = ref('evidence')
const tabs = [
  { key: 'evidence', label: 'Evidence' },
  { key: 'analysis', label: 'AI Analysis' },
  { key: 'actions', label: 'Actions' },
  { key: 'timeline', label: 'Timeline' },
]

const investigation = computed(() => store.currentInvestigation)
const evidence = computed(() => store.evidence)
const analysis = computed(() => store.analysis)
const actions = computed(() => store.actions)

onMounted(() => {
  store.fetchInvestigationDetail(route.params.id)
})

watch(() => route.params.id, (newId) => {
  if (newId) store.fetchInvestigationDetail(newId)
})

function formatDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function timeAgo(dateStr) {
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now - date) / 1000)
  const intervals = [
    { label: 'year', seconds: 31536000 },
    { label: 'month', seconds: 2592000 },
    { label: 'day', seconds: 86400 },
    { label: 'hour', seconds: 3600 },
    { label: 'minute', seconds: 60 },
  ]
  for (const { label, seconds: s } of intervals) {
    const count = Math.floor(seconds / s)
    if (count >= 1) return `${count} ${label}${count > 1 ? 's' : ''} ago`
  }
  return 'just now'
}

function formatJson(data) {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

// Timeline: merge evidence, analysis, actions into sorted list
const timeline = computed(() => {
  const items = []

  evidence.value.forEach(e => {
    items.push({
      type: 'evidence',
      title: `Evidence collected: ${e.source_type}`,
      description: e.notes || `Source: ${e.source_id || 'N/A'}`,
      timestamp: e.created_at,
      icon: 'evidence',
    })
  })

  analysis.value.forEach(a => {
    items.push({
      type: 'analysis',
      title: `${a.analysis_type === 'ai' ? 'AI' : 'Manual'} Analysis`,
      description: a.content.substring(0, 150) + (a.content.length > 150 ? '...' : ''),
      timestamp: a.created_at,
      icon: 'analysis',
      confidence: a.confidence,
    })
  })

  actions.value.forEach(a => {
    items.push({
      type: 'action',
      title: `Action: ${a.action_type.replace(/_/g, ' ')}`,
      description: a.reasoning || a.description,
      timestamp: a.created_at,
      icon: 'action',
      status: a.status,
    })
  })

  return items.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
})

const actionTypeIcons = {
  isolate_host: '🔒',
  block_ip: '🚫',
  quarantine_file: '📦',
  notify_user: '📧',
}

async function updateStatus(newStatus) {
  await store.updateInvestigation(route.params.id, { status: newStatus })
}

const starting = ref(false)
const investigateError = ref('')

// Newest analysis first — used to tell a genuinely failed run (verdict
// ERROR, or the investigation somehow never got one at all) from a normal
// completed one, so the retry affordance can be worded appropriately.
const latestAnalysis = computed(() => {
  if (!analysis.value.length) return null
  return [...analysis.value].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  )[0]
})
const investigationFailed = computed(() =>
  investigation.value?.status === 'COMPLETED' &&
  latestAnalysis.value?.verdict === 'ERROR'
)

async function startInvestigation() {
  starting.value = true
  investigateError.value = ''
  try {
    await store.startInvestigation(route.params.id)
  } catch (err) {
    investigateError.value = err.message || 'Failed to start investigation.'
  } finally {
    starting.value = false
  }
}

async function retryInvestigation() {
  // Re-running an already-completed investigation adds a new analysis
  // rather than replacing the old one (evidence/actions/analysis are kept
  // as history — see investigator.py) — worth a confirmation so it isn't
  // triggered by a stray click, except when the prior run simply failed.
  if (!investigationFailed.value && !confirm(
    'Re-run the AI investigation? The previous analysis and evidence stay '
    + 'on record; this adds a new attempt rather than replacing it.'
  )) return
  await startInvestigation()
}

const deleting = ref(false)

async function deleteInvestigation() {
  if (!confirm('Delete this investigation? This permanently removes its evidence, analysis, and actions too.')) return
  deleting.value = true
  try {
    await store.deleteInvestigation(route.params.id)
    router.push('/investigations')
  } catch (err) {
    investigateError.value = err.message || 'Failed to delete investigation.'
  } finally {
    deleting.value = false
  }
}

const verdictStyles = {
  TRUE_POSITIVE: 'bg-severity-high/15 text-severity-high',
  FALSE_POSITIVE: 'bg-severity-low/15 text-severity-low',
  NEEDS_REVIEW: 'bg-severity-medium/15 text-severity-medium',
  ERROR: 'bg-severity-critical/15 text-severity-critical',
}
</script>

<template>
  <div class="space-y-6">
    <LoadingSpinner v-if="store.loading && !investigation" />

    <template v-if="investigation">
      <!-- Header -->
      <div>
        <button class="btn-ghost text-xs mb-3" @click="router.push('/investigations')">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back to Investigations
        </button>

        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div class="min-w-0">
            <h1 class="text-xl font-bold text-surface-100 leading-tight">{{ investigation.title }}</h1>
            <p class="text-sm text-surface-400 mt-1">{{ investigation.description }}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <SeverityBadge :severity="investigation.severity" />
            <StatusBadge :status="investigation.status" />
          </div>
        </div>

        <!-- Quick actions -->
        <div class="flex flex-wrap items-center gap-2 mt-4">
          <button
            v-if="investigation.status === 'QUEUED'"
            class="btn-primary text-xs"
            :disabled="starting"
            @click="startInvestigation"
          >
            {{ starting ? 'Starting…' : '🤖 Start Investigation' }}
          </button>
          <span
            v-if="investigation.status === 'IN_PROGRESS'"
            class="badge bg-accent/15 text-accent text-xs animate-pulse"
          >
            🤖 AI investigating…
          </span>
          <template v-if="investigation.status === 'COMPLETED'">
            <span v-if="investigationFailed" class="badge bg-severity-critical/15 text-severity-critical text-xs">
              ⚠️ Investigation failed
            </span>
            <button
              class="text-xs"
              :class="investigationFailed ? 'btn-primary' : 'btn-ghost'"
              :disabled="starting"
              @click="retryInvestigation"
            >
              {{ starting ? 'Starting…' : (investigationFailed ? '🔄 Retry Investigation' : '🔄 Re-run Investigation') }}
            </button>
            <button
              class="btn-secondary text-xs"
              @click="updateStatus('CLOSED')"
            >
              Close Investigation
            </button>
          </template>
          <button
            v-if="investigation.status === 'CLOSED'"
            class="btn-ghost text-xs"
            @click="updateStatus('COMPLETED')"
          >
            Reopen
          </button>
          <button
            class="btn-danger text-xs ml-auto"
            :disabled="deleting"
            @click="deleteInvestigation"
          >
            {{ deleting ? 'Deleting…' : 'Delete Investigation' }}
          </button>
          <span v-if="investigateError" class="text-xs text-severity-critical w-full">{{ investigateError }}</span>
          <span v-else-if="store.error && investigation.status === 'IN_PROGRESS'" class="text-xs text-severity-medium w-full">{{ store.error }}</span>
        </div>
      </div>

      <!-- Investigation Info -->
      <div class="card-padded">
        <h2 class="section-title mb-4">Investigation Info</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p class="label">Alert ID</p>
            <p class="text-sm font-mono text-surface-300">{{ investigation.alert_id || '—' }}</p>
          </div>
          <div>
            <p class="label">Created</p>
            <p class="text-sm text-surface-300">{{ formatDate(investigation.created_at) }}</p>
          </div>
          <div>
            <p class="label">Last Updated</p>
            <p class="text-sm text-surface-300">{{ timeAgo(investigation.updated_at) }}</p>
          </div>
          <div>
            <p class="label">Closed At</p>
            <p class="text-sm text-surface-300">{{ formatDate(investigation.closed_at) }}</p>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div>
        <div class="flex border-b border-surface-700">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px"
            :class="activeTab === tab.key
              ? 'text-accent border-accent'
              : 'text-surface-500 border-transparent hover:text-surface-300 hover:border-surface-600'"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
            <span
              v-if="tab.key === 'evidence'"
              class="ml-1.5 text-xs text-surface-600"
            >{{ evidence.length }}</span>
            <span
              v-if="tab.key === 'analysis'"
              class="ml-1.5 text-xs text-surface-600"
            >{{ analysis.length }}</span>
            <span
              v-if="tab.key === 'actions'"
              class="ml-1.5 text-xs text-surface-600"
            >{{ actions.length }}</span>
          </button>
        </div>

        <!-- Evidence Tab -->
        <div v-if="activeTab === 'evidence'" class="mt-5 space-y-4">
          <div v-if="evidence.length === 0" class="text-sm text-surface-500 py-8 text-center">
            No evidence collected yet.
          </div>
          <div v-for="ev in evidence" :key="ev.id" class="card-padded">
            <div class="flex items-start justify-between mb-3">
              <div>
                <span class="badge bg-surface-700 text-surface-300">{{ ev.source_type }}</span>
                <span v-if="ev.source_id" class="ml-2 text-xs font-mono text-surface-500">{{ ev.source_id }}</span>
              </div>
              <span class="text-xs text-surface-500">{{ formatDate(ev.created_at) }}</span>
            </div>
            <p v-if="ev.notes" class="text-sm text-surface-400 mb-3 italic">{{ ev.notes }}</p>
            <div v-if="ev.data" class="bg-surface-950 rounded-md p-4 overflow-x-auto">
              <pre class="text-xs font-mono text-surface-400 leading-relaxed whitespace-pre-wrap">{{ formatJson(ev.data) }}</pre>
            </div>
          </div>
        </div>

        <!-- AI Analysis Tab -->
        <div v-if="activeTab === 'analysis'" class="mt-5 space-y-4">
          <div v-if="analysis.length === 0" class="text-sm text-surface-500 py-8 text-center">
            No analysis performed yet.
          </div>
          <div v-for="an in analysis" :key="an.id" class="card-padded">
            <div class="flex items-start justify-between mb-4">
              <div class="flex items-center gap-2">
                <span class="badge bg-accent/15 text-accent">
                  {{ an.analysis_type === 'ai' ? '🤖 AI Analysis' : an.analysis_type }}
                </span>
                <span
                  v-if="an.verdict"
                  class="badge"
                  :class="verdictStyles[an.verdict] || 'bg-surface-700 text-surface-300'"
                >
                  {{ an.verdict.replace(/_/g, ' ') }}
                </span>
                <span v-if="an.model_id" class="text-xs font-mono text-surface-500">{{ an.model_id }}</span>
              </div>
              <span class="text-xs text-surface-500">{{ formatDate(an.created_at) }}</span>
            </div>

            <!-- Confidence -->
            <div v-if="an.confidence != null" class="mb-4">
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-surface-500">Confidence</span>
                <span class="text-xs font-medium" :class="an.confidence >= 0.8 ? 'text-severity-low' : an.confidence >= 0.5 ? 'text-severity-medium' : 'text-severity-high'">{{ Math.round(an.confidence * 100) }}%</span>
              </div>
              <div class="h-1.5 bg-surface-800 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="an.confidence >= 0.8 ? 'bg-severity-low' : an.confidence >= 0.5 ? 'bg-severity-medium' : 'bg-severity-high'"
                  :style="{ width: (an.confidence * 100) + '%' }"
                />
              </div>
            </div>

            <!-- Content -->
            <div class="markdown-content text-sm text-surface-300" v-html="renderMarkdown(an.content)" />
          </div>
        </div>

        <!-- Actions Tab -->
        <div v-if="activeTab === 'actions'" class="mt-5 space-y-3">
          <div v-if="actions.length === 0" class="text-sm text-surface-500 py-8 text-center">
            No actions performed yet.
          </div>
          <div v-for="act in actions" :key="act.id" class="card">
            <div class="p-4 flex items-start gap-3">
              <span class="text-lg mt-0.5">{{ actionTypeIcons[act.action_type] || '⚡' }}</span>
              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <h4 class="text-sm font-medium text-surface-200">
                      {{ act.action_type.replace(/_/g, ' ') }}
                    </h4>
                    <p class="text-xs text-surface-400 mt-0.5">{{ act.description }}</p>
                  </div>
                  <StatusBadge :status="act.status" />
                </div>

                <div v-if="act.reasoning" class="mt-3 border-l-2 border-accent/40 pl-3">
                  <p class="text-xs text-surface-300 leading-relaxed italic">{{ act.reasoning }}</p>
                </div>

                <div v-if="act.result" class="mt-3 bg-surface-950 rounded-md p-3">
                  <p class="text-xs font-mono text-surface-400">{{ act.result }}</p>
                </div>

                <div class="flex items-center gap-4 mt-2 text-xs text-surface-500">
                  <span>Created: {{ formatDate(act.created_at) }}</span>
                  <span v-if="act.completed_at">Completed: {{ formatDate(act.completed_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Timeline Tab -->
        <div v-if="activeTab === 'timeline'" class="mt-5">
          <div v-if="timeline.length === 0" class="text-sm text-surface-500 py-8 text-center">
            No activity recorded yet.
          </div>
          <div v-else class="relative">
            <!-- Vertical line -->
            <div class="absolute left-[15px] top-2 bottom-2 w-px bg-surface-700" />

            <div
              v-for="(item, idx) in timeline"
              :key="idx"
              class="relative flex gap-4 pb-6 last:pb-0"
            >
              <!-- Dot -->
              <div
                class="w-[31px] shrink-0 flex justify-center"
              >
                <div
                  class="w-2.5 h-2.5 rounded-full mt-1.5 ring-4 ring-surface-950 z-10"
                  :class="{
                    'bg-accent': item.type === 'evidence',
                    'bg-status-investigating': item.type === 'analysis',
                    'bg-severity-medium': item.type === 'action' && item.status === 'pending',
                    'bg-severity-low': item.type === 'action' && item.status === 'completed',
                    'bg-severity-critical': item.type === 'action' && item.status === 'failed',
                  }"
                />
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-surface-200">{{ item.title }}</p>
                    <p class="text-xs text-surface-400 mt-0.5 line-clamp-2">{{ item.description }}</p>
                  </div>
                  <span class="text-xs text-surface-500 shrink-0">{{ timeAgo(item.timestamp) }}</span>
                </div>
                <div v-if="item.confidence != null" class="mt-1">
                  <span class="text-xs text-surface-500">Confidence: {{ Math.round(item.confidence * 100) }}%</span>
                </div>
                <StatusBadge v-if="item.status" :status="item.status" class="mt-1" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
