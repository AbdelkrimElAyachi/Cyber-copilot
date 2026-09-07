<script setup>
import { onMounted, ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat.js'
import LoadingSpinner from '../components/common/LoadingSpinner.vue'
import EmptyState from '../components/common/EmptyState.vue'

const store = useChatStore()
const draft = ref('')
const messagesEl = ref(null)
const expandedTrace = ref(new Set())

onMounted(async () => {
  await store.fetchSessions()
  if (store.sessions.length > 0) {
    await store.selectSession(store.sessions[0].id)
  }
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

watch(() => store.messages.length, scrollToBottom)

async function newChat() {
  await store.createSession()
  draft.value = ''
  scrollToBottom()
}

async function pickSession(id) {
  if (id === store.currentSessionId) return
  await store.selectSession(id)
  scrollToBottom()
}

async function deleteSession(id) {
  if (!confirm('Delete this chat?')) return
  await store.deleteSession(id)
}

async function send() {
  const text = draft.value.trim()
  if (!text || store.sending) return
  if (!store.currentSessionId) {
    await store.createSession()
  }
  draft.value = ''
  scrollToBottom()
  try {
    await store.sendMessage(text)
  } catch {
    // store.error is already set and shown below the input.
  }
  scrollToBottom()
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function toggleTrace(id) {
  const next = new Set(expandedTrace.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedTrace.value = next
}

function timeAgo(dateStr) {
  const seconds = Math.floor((new Date() - new Date(dateStr)) / 1000)
  const intervals = [
    { label: 'y', seconds: 31536000 }, { label: 'mo', seconds: 2592000 },
    { label: 'd', seconds: 86400 }, { label: 'h', seconds: 3600 }, { label: 'm', seconds: 60 },
  ]
  for (const { label, seconds: s } of intervals) {
    const count = Math.floor(seconds / s)
    if (count >= 1) return `${count}${label} ago`
  }
  return 'just now'
}

const hasTools = (m) => Array.isArray(m.tool_trace) ? m.tool_trace.length > 0 : !!m.tool_trace
const parsedTrace = computed(() => (m) => {
  if (!m.tool_trace) return []
  return typeof m.tool_trace === 'string' ? JSON.parse(m.tool_trace) : m.tool_trace
})
</script>

<template>
  <div class="flex h-[calc(100vh-8rem)] gap-4">
    <!-- Session list -->
    <div class="w-64 shrink-0 card flex flex-col overflow-hidden">
      <div class="p-3 border-b border-surface-700/50">
        <button class="btn-primary w-full text-xs" @click="newChat">+ New chat</button>
      </div>
      <div class="flex-1 overflow-y-auto">
        <LoadingSpinner v-if="store.loadingSessions" size="sm" />
        <div v-else-if="store.sessions.length === 0" class="text-xs text-surface-500 text-center py-6 px-3">
          No chats yet — start one above.
        </div>
        <div
          v-for="s in store.sessions"
          :key="s.id"
          class="group flex items-center gap-2 px-3 py-2.5 cursor-pointer border-b border-surface-800/60"
          :class="s.id === store.currentSessionId ? 'bg-accent/10' : 'hover:bg-surface-800/60'"
          @click="pickSession(s.id)"
        >
          <div class="min-w-0 flex-1">
            <p class="text-sm truncate" :class="s.id === store.currentSessionId ? 'text-accent font-medium' : 'text-surface-200'">
              {{ s.title }}
            </p>
            <p class="text-[11px] text-surface-500">{{ timeAgo(s.updated_at) }}</p>
          </div>
          <button
            class="opacity-0 group-hover:opacity-100 text-surface-500 hover:text-severity-critical shrink-0"
            title="Delete chat"
            @click.stop="deleteSession(s.id)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3.5 h-3.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Conversation -->
    <div class="flex-1 card flex flex-col overflow-hidden">
      <template v-if="!store.currentSessionId">
        <EmptyState
          title="AI Security Assistant"
          message="Ask about alerts, investigations, or assets — start a new chat to begin."
        />
      </template>

      <template v-else>
        <div ref="messagesEl" class="flex-1 overflow-y-auto p-4 space-y-4">
          <LoadingSpinner v-if="store.loadingMessages" />

          <div
            v-for="m in store.messages"
            :key="m.id"
            class="flex"
            :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="max-w-[75%] rounded-lg px-4 py-2.5"
              :class="m.role === 'user' ? 'bg-accent text-white' : 'bg-surface-800 text-surface-200'"
            >
              <p class="text-sm whitespace-pre-wrap leading-relaxed">{{ m.content }}</p>

              <div v-if="m.role === 'assistant' && m.reasoning" class="mt-2 pt-2 border-t border-surface-700/60">
                <p class="text-xs italic text-surface-400 leading-relaxed">{{ m.reasoning }}</p>
              </div>

              <div v-if="m.role === 'assistant' && hasTools(m)" class="mt-2">
                <button
                  class="text-[11px] text-accent hover:underline"
                  @click="toggleTrace(m.id)"
                >
                  🔧 {{ parsedTrace(m).length }} tool call{{ parsedTrace(m).length !== 1 ? 's' : '' }}
                  {{ expandedTrace.has(m.id) ? '▲' : '▼' }}
                </button>
                <div v-if="expandedTrace.has(m.id)" class="mt-2 space-y-1.5">
                  <div
                    v-for="(t, idx) in parsedTrace(m)"
                    :key="idx"
                    class="bg-surface-950 rounded-md p-2 text-[11px] font-mono text-surface-400"
                  >
                    <span class="text-accent">{{ t.tool }}</span>({{ JSON.stringify(t.arguments) }})
                    <div class="text-surface-500 mt-1 truncate">→ {{ t.result_summary }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="store.sending" class="flex justify-start">
            <div class="bg-surface-800 rounded-lg px-4 py-2.5">
              <span class="text-sm text-surface-400 animate-pulse">Thinking…</span>
            </div>
          </div>
        </div>

        <div class="border-t border-surface-700/50 p-3">
          <p v-if="store.error" class="text-xs text-severity-critical mb-2">{{ store.error }}</p>
          <div class="flex items-end gap-2">
            <textarea
              v-model="draft"
              rows="1"
              class="input-field flex-1 resize-none"
              placeholder="Ask about an alert, investigation, or asset…"
              :disabled="store.sending"
              @keydown="onKeydown"
            />
            <button
              class="btn-primary text-xs shrink-0"
              :disabled="store.sending || !draft.trim()"
              @click="send"
            >
              Send
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
