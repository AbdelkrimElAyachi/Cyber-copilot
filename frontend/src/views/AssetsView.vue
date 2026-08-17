<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAssetsStore } from '../stores/assets.js'
import { useInvestigationsStore } from '../stores/investigations.js'
import SeverityBadge from '../components/common/SeverityBadge.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'

const assetsStore = useAssetsStore()
const investigationsStore = useInvestigationsStore()

const selectedAsset = ref(null)

onMounted(() => {
  assetsStore.fetchAssets()
  investigationsStore.fetchInvestigations()
})

const assets = computed(() => assetsStore.filteredAssets)

const relatedInvestigations = computed(() => {
  if (!selectedAsset.value) return []
  const asset = selectedAsset.value
  return investigationsStore.investigations.filter(inv => {
    const searchStr = `${inv.title} ${inv.description}`.toLowerCase()
    return searchStr.includes(asset.hostname.toLowerCase()) ||
      (asset.ip_address && searchStr.includes(asset.ip_address))
  })
})

const assetTypeLabels = {
  endpoint: 'Endpoint',
  server: 'Server',
  firewall: 'Firewall',
  cloud: 'Cloud',
  network: 'Network',
}

function selectAsset(asset) {
  selectedAsset.value = selectedAsset.value?.id === asset.id ? null : asset
}
</script>

<template>
  <div class="space-y-5">
    <!-- Filters -->
    <div class="card-padded">
      <div class="flex flex-wrap items-center gap-4">
        <div>
          <label class="label">Type</label>
          <select
            class="select-field w-40"
            :value="assetsStore.filters.asset_type"
            @change="assetsStore.setFilter('asset_type', $event.target.value)"
          >
            <option value="">All Types</option>
            <option value="endpoint">Endpoint</option>
            <option value="server">Server</option>
            <option value="firewall">Firewall</option>
            <option value="cloud">Cloud</option>
            <option value="network">Network</option>
          </select>
        </div>
        <div>
          <label class="label">Criticality</label>
          <select
            class="select-field w-40"
            :value="assetsStore.filters.criticality"
            @change="assetsStore.setFilter('criticality', $event.target.value)"
          >
            <option value="">All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div class="flex items-end">
          <button
            v-if="assetsStore.filters.asset_type || assetsStore.filters.criticality"
            class="btn-ghost text-xs"
            @click="assetsStore.clearFilters()"
          >Clear filters</button>
        </div>
        <span class="ml-auto text-sm text-surface-500">{{ assets.length }} asset{{ assets.length !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <LoadingSpinner v-if="assetsStore.loading" />

    <EmptyState v-else-if="assets.length === 0" title="No assets found" message="No assets match your current filters." />

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        v-for="asset in assets"
        :key="asset.id"
        class="card cursor-pointer transition-colors duration-150"
        :class="selectedAsset?.id === asset.id ? 'ring-1 ring-accent/50 bg-surface-800/50' : 'hover:bg-surface-800/40'"
        @click="selectAsset(asset)"
      >
        <div class="p-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="text-sm font-medium text-surface-100 font-mono">{{ asset.hostname }}</h3>
              <p class="text-xs text-surface-500 mt-0.5">{{ asset.ip_address || 'No IP' }}</p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span class="badge bg-surface-700 text-surface-300">{{ assetTypeLabels[asset.asset_type] || asset.asset_type }}</span>
              <SeverityBadge :severity="asset.criticality" />
            </div>
          </div>

          <div class="flex items-center gap-4 mt-3 text-xs text-surface-500">
            <span v-if="asset.os">{{ asset.os }}</span>
            <span v-if="asset.wazuh_agent_id" class="font-mono">Agent: {{ asset.wazuh_agent_id }}</span>
          </div>
        </div>

        <!-- Expanded detail -->
        <div v-if="selectedAsset?.id === asset.id" class="border-t border-surface-700 p-4 bg-surface-950/50">
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p class="label">Hostname</p>
              <p class="font-mono text-surface-300">{{ asset.hostname }}</p>
            </div>
            <div>
              <p class="label">IP Address</p>
              <p class="font-mono text-surface-300">{{ asset.ip_address || '—' }}</p>
            </div>
            <div>
              <p class="label">Operating System</p>
              <p class="text-surface-300">{{ asset.os || '—' }}</p>
            </div>
            <div>
              <p class="label">Wazuh Agent</p>
              <p class="font-mono text-surface-300">{{ asset.wazuh_agent_id || '—' }}</p>
            </div>
          </div>
          <div v-if="asset.notes" class="mt-3">
            <p class="label">Notes</p>
            <p class="text-sm text-surface-400">{{ asset.notes }}</p>
          </div>

          <!-- Related investigations -->
          <div class="mt-4">
            <p class="label">Related Investigations</p>
            <div v-if="relatedInvestigations.length === 0" class="text-xs text-surface-500 mt-1">
              No related investigations found.
            </div>
            <div v-else class="mt-2 space-y-2">
              <router-link
                v-for="inv in relatedInvestigations"
                :key="inv.id"
                :to="`/investigations/${inv.id}`"
                class="block p-2.5 rounded-md bg-surface-800/50 hover:bg-surface-800 transition-colors"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-medium text-surface-200 truncate">{{ inv.title }}</p>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <SeverityBadge :severity="inv.severity" />
                    <StatusBadge :status="inv.status" />
                  </div>
                </div>
              </router-link>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
