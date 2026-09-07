import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Fired by api/client.js when a request comes back 401 (expired/invalid
// token) — the token is already cleared at that point, this just moves
// the user to the login screen instead of leaving a dead page up.
window.addEventListener('auth:unauthorized', () => {
  if (router.currentRoute.value.name !== 'login') {
    router.push({ name: 'login' })
  }
})

app.mount('#app')
