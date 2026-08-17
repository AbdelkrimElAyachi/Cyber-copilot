<script setup>
defineProps({
  open: Boolean,
  title: {
    type: String,
    default: 'Confirm Action',
  },
  message: {
    type: String,
    default: 'Are you sure you want to proceed?',
  },
  confirmLabel: {
    type: String,
    default: 'Confirm',
  },
  danger: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['confirm', 'cancel'])
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-150"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
        <div class="fixed inset-0 bg-black/60" @click="$emit('cancel')" />
        <div class="relative bg-surface-900 border border-surface-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
          <h3 class="text-base font-semibold text-surface-100">{{ title }}</h3>
          <p class="text-sm text-surface-400 mt-2">{{ message }}</p>
          <div class="flex justify-end gap-3 mt-6">
            <button class="btn-secondary" @click="$emit('cancel')">Cancel</button>
            <button
              :class="danger ? 'btn-danger' : 'btn-primary'"
              @click="$emit('confirm')"
            >
              {{ confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
