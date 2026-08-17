<script setup>
defineProps({
  title: {
    type: String,
    default: 'No data',
  },
  message: {
    type: String,
    default: 'No items to display.',
  },
})
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 text-center">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" class="w-12 h-12 text-surface-600 mb-4">
      <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 11.625l2.25-2.25M12 11.625l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
    </svg>
    <h3 class="text-sm font-medium text-surface-300">{{ title }}</h3>
    <p class="text-sm text-surface-500 mt-1">{{ message }}</p>
  </div>
</template>
