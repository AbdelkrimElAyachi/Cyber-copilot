<script setup>
const props = defineProps({
  severity: {
    type: String,
    required: true,
    validator: v => ['critical', 'high', 'medium', 'low'].includes(v),
  },
})

const badgeClass = {
  critical: 'badge-severity-critical',
  high: 'badge-severity-high',
  medium: 'badge-severity-medium',
  low: 'badge-severity-low',
}
</script>

<template>
  <span :class="badgeClass[severity]">
    {{ severity }}
  </span>
</template>
