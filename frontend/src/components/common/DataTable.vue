<script setup>
defineProps({
  columns: {
    type: Array,
    required: true,
    // Each column: { key: string, label: string, class?: string }
  },
  rows: {
    type: Array,
    default: () => [],
  },
  clickable: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['row-click'])
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-surface-700">
          <th
            v-for="col in columns"
            :key="col.key"
            class="text-left py-3 px-4 text-xs font-medium text-surface-500 uppercase tracking-wider"
            :class="col.class"
          >
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in rows"
          :key="row.id || index"
          class="table-row"
          :class="{ 'cursor-pointer': clickable }"
          @click="clickable && $emit('row-click', row)"
        >
          <td
            v-for="col in columns"
            :key="col.key"
            class="py-3 px-4"
            :class="col.class"
          >
            <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
              {{ row[col.key] }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
