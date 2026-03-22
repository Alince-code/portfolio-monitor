<script setup>
import { onMounted, ref } from 'vue'
import { hasAuthSession, setAuthSession } from './auth'

const API = ''

const form = ref({ username: 'admin', password: 'admin123' })
const loginLoading = ref(false)
const loginError = ref('')

function getTgInitData() {
  return window.Telegram?.WebApp?.initData || ''
}

async function loginUser() {
  loginLoading.value = true
  loginError.value = ''

  try {
    const headers = { 'Content-Type': 'application/json' }
    const tgInitData = getTgInitData()
    if (tgInitData) headers['X-Telegram-Init-Data'] = tgInitData

    const res = await fetch(API + '/api/auth/login', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        username: form.value.username,
        password: form.value.password,
      }),
    })

    if (!res.ok) {
      const error = await res.json().catch(() => null)
      throw new Error(error?.detail || '登录失败，请检查用户名和密码')
    }

    const data = await res.json()
    setAuthSession(data.access_token, data.user)
    window.location.replace('/')
  } catch (error) {
    loginError.value = error.message || '登录失败，请检查用户名和密码'
  } finally {
    loginLoading.value = false
  }
}

onMounted(() => {
  if (hasAuthSession()) {
    window.location.replace('/')
  }
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <div class="auth-brand">Portfolio Monitor</div>
      <h1>登录系统</h1>
      <p class="auth-subtitle">登录页与主系统页面已拆分，登录后进入独立前端页面。</p>

      <div class="auth-default-user">
        <span>默认用户</span>
        <strong>admin / admin123</strong>
      </div>

      <form class="auth-form" @submit.prevent="loginUser">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            required
          >
        </div>

        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            required
          >
        </div>

        <div v-if="loginError" class="auth-error">{{ loginError }}</div>

        <button class="auth-submit" type="submit" :disabled="loginLoading">
          {{ loginLoading ? '登录中...' : '进入系统' }}
        </button>
      </form>
    </div>
  </div>
</template>
