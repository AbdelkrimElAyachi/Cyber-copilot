<script setup>
const props = defineProps({
  status: {
    type: String,
    required: true,
  },
})

const statusMap = {
  QUEUED: { class: 'badge-status-queued', label: 'Queued' },
  INVESTIGATING: { class: 'badge-status-investigating', label: 'Investigating' },
  CLOSED: { class: 'badge-status-closed', label: 'Closed' },
  pending: { class: 'badge bg-amber-500/15 text-amber-400', label: 'Pending' },
  completed: { class: 'badge bg-emerald-500/15 text-emerald-400', label: 'Completed' },
  failed: { class: 'badge bg-red-500/15 text-red-400', label: 'Failed' },
}

const info = statusMap[props.status] || { class: 'badge bg-surface-600/20 text-surface-400', label: props.status }
</script>

<template>
  <span :class="info.class">{{ info.label }}</span>
</template>
