<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

defineEmits(['toggle-sidebar'])

const route = useRoute()

const pageTitle = computed(() => route.meta.title || 'Page')
</script>

<template>
  <header class="h-16 bg-surface-900/80 backdrop-blur-sm border-b border-surface-700/50 flex items-center justify-between px-6 shrink-0 sticky top-0 z-30">
    <div class="flex items-center gap-4">
      <!-- Mobile hamburger -->
      <button
        class="lg:hidden btn-ghost p-1.5 -ml-1.5"
        @click="$emit('toggle-sidebar')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        </svg>
      </button>

      <h1 class="text-lg font-semibold text-surface-100">{{ pageTitle }}</h1>
    </div>

    <div class="flex items-center gap-3">
      <!-- Status indicator -->
      <div class="hidden sm:flex items-center gap-2 text-xs text-surface-500">
        <span class="w-1.5 h-1.5 rounded-full bg-severity-low animate-pulse" />
        System Operational
      </div>
    </div>
  </header>
</template>
