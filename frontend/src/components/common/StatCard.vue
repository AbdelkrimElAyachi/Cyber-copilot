<script setup>
defineProps({
  title: String,
  value: [String, Number],
  subtitle: String,
  color: {
    type: String,
    default: 'accent',
  },
})

const colorMap = {
  accent: 'text-accent',
  critical: 'text-severity-critical',
  high: 'text-severity-high',
  medium: 'text-severity-medium',
  low: 'text-severity-low',
  queued: 'text-status-queued',
  investigating: 'text-status-investigating',
  closed: 'text-status-closed',
}
</script>

<template>
  <div class="card-padded">
    <p class="text-xs font-medium text-surface-500 uppercase tracking-wider">{{ title }}</p>
    <p class="text-2xl font-bold mt-1" :class="colorMap[color] || 'text-surface-100'">{{ value }}</p>
    <p v-if="subtitle" class="text-xs text-surface-500 mt-1">{{ subtitle }}</p>
  </div>
</template>
