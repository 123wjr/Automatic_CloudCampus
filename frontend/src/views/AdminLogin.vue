<template>
  <div class="login-view">
    <div class="login-card">
      <h2>管理员登录</h2>
      <p class="hint">用于管理课程、排除任务列表及查看统计数据</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username">管理员账号</label>
          <input id="username" v-model="username" type="text" placeholder="请输入管理员账号" required />
        </div>

        <div class="form-group">
          <label for="password">管理员密码</label>
          <input id="password" v-model="password" type="password" placeholder="请输入管理员密码" required />
        </div>

        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import * as api from '../services/api.js'

const router = useRouter()
const store = useAppStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.adminLogin(username.value, password.value)
    if (res.data.success) {
      store.setAdminToken(res.data.token)
      router.push('/admin')
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '管理员登录失败'
  } finally {
    loading.value = false
  }
}
</script>
