import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: 'Dashboard' },
  },
  {
    path: '/investigations',
    name: 'investigations',
    component: () => import('../views/InvestigationsView.vue'),
    meta: { title: 'Investigations' },
  },
  {
    path: '/investigations/:id',
    name: 'investigation-detail',
    component: () => import('../views/InvestigationDetailView.vue'),
    meta: { title: 'Investigation Detail' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { title: 'AI Assistant' },
  },
  {
    path: '/policies',
    name: 'policies',
    component: () => import('../views/PoliciesView.vue'),
    meta: { title: 'Policies' },
  },
  {
    path: '/assets',
    name: 'assets',
    component: () => import('../views/AssetsView.vue'),
    meta: { title: 'Assets' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: 'Settings' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  document.title = `${to.meta.title || 'Page'} — CyberCopilot`
})

export default router
