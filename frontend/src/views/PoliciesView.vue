<script setup>
import { ref, onMounted, computed } from 'vue'
import { usePoliciesStore } from '../stores/policies.js'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'
import EmptyState from '../components/common/EmptyState.vue'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'

const store = usePoliciesStore()

onMounted(() => {
  store.fetchPolicies()
})

const policies = computed(() => store.sortedPolicies)

// Form state
const showForm = ref(false)
const editingId = ref(null)
const form = ref({
  name: '',
  description: '',
  priority: 0,
  min_level: '',
  rule_ids: '',
})

function openCreateForm() {
  editingId.value = null
  form.value = { name: '', description: '', priority: 0, min_level: '', rule_ids: '' }
  showForm.value = true
}

function openEditForm(policy) {
  editingId.value = policy.id
  form.value = {
    name: policy.name,
    description: policy.description || '',
    priority: policy.priority,
    min_level: policy.conditions?.min_level || '',
    rule_ids: (policy.conditions?.rule_ids || []).join(', '),
  }
  showForm.value = true
}

async function submitForm() {
  const conditions = {}
  if (form.value.min_level) {
    conditions.min_level = parseInt(form.value.min_level)
  }
  if (form.value.rule_ids.trim()) {
    conditions.rule_ids = form.value.rule_ids.split(',').map(s => s.trim()).filter(Boolean)
  }

  const payload = {
    name: form.value.name,
    description: form.value.description,
    priority: parseInt(form.value.priority) || 0,
    conditions,
  }

  if (editingId.value) {
    await store.updatePolicy(editingId.value, payload)
  } else {
    payload.is_enabled = true
    await store.createPolicy(payload)
  }

  showForm.value = false
  await store.fetchPolicies()
}

async function handleToggle(policy) {
  await store.togglePolicy(policy.id, !policy.is_enabled)
}

// Delete confirmation
const deleteTarget = ref(null)

async function confirmDelete() {
  if (deleteTarget.value) {
    await store.removePolicy(deleteTarget.value.id)
    deleteTarget.value = null
  }
}

function conditionsSummary(conditions) {
  const parts = []
  if (conditions?.min_level) parts.push(`Level ≥ ${conditions.min_level}`)
  if (conditions?.rule_ids?.length) parts.push(`${conditions.rule_ids.length} rule ID${conditions.rule_ids.length > 1 ? 's' : ''}`)
  return parts.length ? parts.join(' · ') : 'No conditions'
}
</script>

<template>
  <div class="space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <p class="text-sm text-surface-400">{{ policies.length }} polic{{ policies.length !== 1 ? 'ies' : 'y' }}</p>
      <button class="btn-primary" @click="openCreateForm">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
        Create Policy
      </button>
    </div>

    <!-- Form -->
    <div v-if="showForm" class="card-padded">
      <h2 class="section-title mb-4">{{ editingId ? 'Edit Policy' : 'Create Policy' }}</h2>
      <form @submit.prevent="submitForm" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="label">Name</label>
            <input v-model="form.name" class="input-field" placeholder="Policy name" required />
          </div>
          <div>
            <label class="label">Priority</label>
            <input v-model="form.priority" type="number" class="input-field" placeholder="0" />
          </div>
        </div>
        <div>
          <label class="label">Description</label>
          <input v-model="form.description" class="input-field" placeholder="Brief description" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="label">Minimum Rule Level</label>
            <input v-model="form.min_level" type="number" class="input-field" placeholder="e.g. 10" min="1" max="16" />
          </div>
          <div>
            <label class="label">Rule IDs (comma-separated)</label>
            <input v-model="form.rule_ids" class="input-field" placeholder="e.g. 5710, 5712, 87101" />
          </div>
        </div>
        <div class="flex items-center gap-3 pt-2">
          <button type="submit" class="btn-primary">{{ editingId ? 'Update' : 'Create' }}</button>
          <button type="button" class="btn-ghost" @click="showForm = false">Cancel</button>
        </div>
      </form>
    </div>

    <!-- Loading -->
    <LoadingSpinner v-if="store.loading" />

    <!-- Empty -->
    <EmptyState v-else-if="policies.length === 0" title="No policies" message="Create a policy to start auto-investigating alerts." />

    <!-- Policy list -->
    <div v-else class="space-y-3">
      <div v-for="policy in policies" :key="policy.id" class="card">
        <div class="p-4 flex items-start gap-4">
          <!-- Toggle -->
          <button
            class="mt-0.5 relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200"
            :class="policy.is_enabled ? 'bg-accent' : 'bg-surface-600'"
            @click="handleToggle(policy)"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200"
              :class="policy.is_enabled ? 'translate-x-4' : 'translate-x-0'"
            />
          </button>

          <div class="flex-1 min-w-0">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="text-sm font-medium text-surface-100">
                  {{ policy.name }}
                  <span class="ml-2 text-xs font-mono text-surface-600">P{{ policy.priority }}</span>
                </h3>
                <p v-if="policy.description" class="text-xs text-surface-400 mt-0.5">{{ policy.description }}</p>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button class="btn-ghost text-xs px-2 py-1" @click="openEditForm(policy)">Edit</button>
                <button class="btn-ghost text-xs px-2 py-1 text-red-400 hover:text-red-300" @click="deleteTarget = policy">Delete</button>
              </div>
            </div>

            <!-- Conditions -->
            <div class="mt-2 flex flex-wrap gap-2">
              <span v-if="policy.conditions?.min_level" class="badge bg-surface-700 text-surface-300">
                Level ≥ {{ policy.conditions.min_level }}
              </span>
              <span
                v-for="ruleId in (policy.conditions?.rule_ids || []).slice(0, 5)"
                :key="ruleId"
                class="badge bg-surface-700 text-surface-300 font-mono"
              >
                {{ ruleId }}
              </span>
              <span
                v-if="(policy.conditions?.rule_ids || []).length > 5"
                class="badge bg-surface-700 text-surface-500"
              >
                +{{ policy.conditions.rule_ids.length - 5 }} more
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete confirm -->
    <ConfirmDialog
      :open="!!deleteTarget"
      title="Delete Policy"
      :message="`Are you sure you want to delete '${deleteTarget?.name}'? This action cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      @confirm="confirmDelete"
      @cancel="deleteTarget = null"
    />
  </div>
</template>
