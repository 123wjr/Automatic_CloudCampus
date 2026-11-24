<template>
  <div class="login-view">
    <div class="login-card">
      <div class="login-icon">🔐</div>
      <h2>云校园自动化</h2>
      <p class="hint">登录后先查询课程任务与价格，确认无误再决定是否付费</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label>📧 账号</label>
          <input v-model="account" type="text" placeholder="云校园邮箱/手机号" required autocomplete="username" />
        </div>

        <div class="form-group">
          <label>🔑 密码</label>
          <input v-model="password" type="password" placeholder="云校园登录密码" required autocomplete="current-password" />
          <p class="field-note">
            密码用于登录你的云校园、读取任务进度并提交完成记录；任务执行期间若登录态失效会用它自动重连。仅在信任本服务时使用。
          </p>
        </div>

        <button type="submit" class="btn btn-primary" :disabled="loading">
          <span v-if="loading" class="btn-spinner"></span>
          {{ loading ? '正在登录...' : '登录并查询进度（免费）' }}
        </button>
      </form>

      <p v-if="error" class="error-msg">{{ error }}</p>

      <div class="trust-badges">
        <div class="badge-item">🔎 先查询 · 后付费</div>
        <div class="badge-item">🎯 满分记录回放</div>
        <div class="badge-item">✅ 完成后自动核对</div>
      </div>
    </div>

    <div class="login-intro">
      <div class="intro-card">
        <h3>🚀 三步完成</h3>
        <div class="steps">
          <div class="step"><span class="step-num">1</span>登录查询</div>
          <div class="step-arrow">→</div>
          <div class="step"><span class="step-num">2</span>确认任务与价格</div>
          <div class="step-arrow">→</div>
          <div class="step"><span class="step-num">3</span>支付后自动完成</div>
        </div>
      </div>

      <div class="intro-card">
        <h3>💰 怎么收费</h3>
        <p class="price-line">
          按可执行任务比例计费：基准价
          <strong>¥{{ basePrice }}</strong>
          × (可完成任务 / 课程总任务)。
        </p>
        <ul class="tips">
          <li>登录与查询<strong>免费</strong>，看到任务和金额后再决定是否支付</li>
          <li>只对“已就绪”的任务计费，跳过的任务不收费</li>
        </ul>
      </div>

      <div class="intro-card">
        <h3>💡 做什么 / 不做什么</h3>
        <ul class="tips">
          <li>✅ 自动完成 H5P 互动类任务，完成后回查云校园核对状态</li>
          <li>⏭️ 视频类、需人工作答的任务不处理，也不计费</li>
          <li>⚡ 支付后在后台执行，关闭浏览器或刷新都不影响进度</li>
          <li v-if="contactEmail">📮 有疑问可联系客服：{{ contactEmail }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import * as api from '../services/api.js'

const router = useRouter()
const store = useAppStore()

const account = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const basePrice = ref(20)
const contactEmail = ref('')

onMounted(() => {
  if (store.loadSession()) {
    router.push('/dashboard')
    return
  }
  loadPublicConfig()
})

async function loadPublicConfig() {
  try {
    const res = await api.getPublicConfig()
    if (res.data.base_price) basePrice.value = res.data.base_price
    if (res.data.contact_email) contactEmail.value = res.data.contact_email
  } catch (e) {
    // 配置拉取失败时保留默认展示，不阻塞登录
  }
}

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.login(account.value, password.value)
    if (res.data.success) {
      store.setSession(res.data)
      router.push('/dashboard')
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '账号或密码不正确，请重新输入'
  } finally {
    loading.value = false
  }
}
</script>
