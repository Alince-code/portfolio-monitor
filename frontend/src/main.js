import { createApp } from 'vue'
import App from './App.vue'
import LoginPage from './LoginPage.vue'
import { hasAuthSession } from './auth'
import './style.css'

const path = window.location.pathname
const isLoginPath = path === '/login'
const isAuthenticated = hasAuthSession()

if (!isAuthenticated && !isLoginPath) {
  window.location.replace('/login')
} else if (isAuthenticated && isLoginPath) {
  window.location.replace('/')
} else {
  createApp(isLoginPath ? LoginPage : App).mount('#app')
}
