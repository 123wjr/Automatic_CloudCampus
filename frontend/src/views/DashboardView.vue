<template>
  <div class="dashboard-view">
    <div class="dashboard-header">
      <div class="user-bar">
        <span class="greeting">👋 你好, {{ store.nickname }}</span>
        <div class="bar-actions">
          <button class="btn btn-sm btn-outline" @click="$router.push('/orders')">📋 订单记录</button>
          <span v-if="store.isAdmin" class="admin-badge" @click="goAdmin">管理面板</span>
          <button class="btn btn-sm btn-outline" @click="handleLogout">退出</button>
        </div>
      </div>
    </div>

    <div class="dashboard-content">
      <div v-if="store.replayError" class="error-msg replay-error">
        ⚠️ {{ store.replayError }}
        <span v-if="contactEmail">，如需协助请联系客服 {{ contactEmail }}</span>
      </div>

      <div v-if="loading" class="loading">
        <span class="spinner"></span>
        <p>正在查询课程进度...</p>
      </div>

      <template v-else-if="store.jobStatus && store.jobStatus.status === 'done'">
        <ProgressPanel :isReplaying="false" :message="doneMessage" />
        <div class="success-card">
          <div class="success-icon">🎉</div>
          <h3>恭喜！任务全部完成</h3>
          <p>所有课程任务已自动处理完毕，可以放心退出</p>
          <p class="success-hint">
            建议回云校园核对一次；如有遗漏请联系客服<span v-if="contactEmail"> {{ contactEmail }}</span>
          </p>
        </div>
      </template>

      <template v-else-if="store.jobStatus && ['partial', 'failed', 'stopped'].includes(store.jobStatus.status)">
        <ProgressPanel :isReplaying="false" :message="finalMessage" />
        <div class="result-card warning-card">
          <div class="result-icon">⚠️</div>
          <h3>{{ finalTitle }}</h3>
          <p>{{ finalMessage }}</p>
          <p v-if="remainingCount > 0" class="result-hint">
            当前重新查询到 {{ remainingCount }} 个待处理任务，可以再次重试。
          </p>
          <p v-else class="result-hint">
            系统未查询到可自动处理的剩余任务，请回云校园核对结果。
          </p>
          <div class="action-bar result-actions">
            <button
              class="btn btn-primary btn-lg"
              :disabled="retrying || store.isReplaying"
              @click="handleRetry"
            >
              {{ retrying ? '正在重试...' : '重试剩余任务' }}
            </button>
          </div>
          <p class="success-hint">
            多次重试后仍未完成时，请联系客服<span v-if="contactEmail"> {{ contactEmail }}</span>
          </p>
        </div>
      </template>

      <template v-else-if="store.jobStatus && (store.jobStatus.status === 'running' || store.jobStatus.status === 'pending')">
        <ProgressPanel :isReplaying="true" menu="background" />
        <div class="info-card">
          <p>⚡ 任务正在后台自动执行中，无需保持页面打开</p>
          <p class="info-sub">关闭浏览器或刷新不影响执行进度，完成后重新登录即可查看结果</p>
        </div>
      </template>

      <div v-else-if="store.tasks.length === 0" class="empty-state">
        <div class="empty-icon">✅</div>
        <p>所有任务已完成，没有待处理的任务</p>
        <p class="empty-sub">
          如果认为有遗漏，请联系客服人工处理<span v-if="contactEmail">：{{ contactEmail }}</span>
        </p>
      </div>

      <template v-else>
        <div class="summary-bar">
          <span class="sum-item">📋 待完成: <strong>{{ store.tasks.length }}</strong> 个</span>
          <span class="sum-item">🟢 可执行: <strong>{{ store.validCount }}</strong> 个</span>
          <span v-if="store.skippedCount > 0" class="sum-item info">
            📝 手动处理: {{ store.skippedCount }} 个
          </span>
        </div>

        <TaskList :tasks="store.tasks" />

        <div class="action-bar">
          <button
            class="btn btn-primary btn-lg btn-play"
            :disabled="store.isReplaying || store.validCount === 0"
            @click="handleStartPayment"
          >
            <template v-if="store.validCount === 0">
              没有可执行的任务
            </template>
            <template v-else>
              🚀 确认支付并开始 ({{ store.validCount }} 个任务)
            </template>
          </button>
        </div>

        <div class="payment-hint">
          <p>💳 仅对上方”已就绪”的任务按比例计费，手动处理的任务不另收费</p>
          <p>🔒 支付由支付宝官方处理，我们不留存您的支付信息</p>
          <p>📮 任务失败或有疑问可联系客服<span v-if="contactEmail"> {{ contactEmail }}</span>，我们会协助重试或处理</p>
          <p class="warn-text" style="font-size:0.82rem">⚠️ 执行期间请勿自行登录云校园，否则登录态会失效、任务可能无法继续</p>
        </div>
      </template>

      <ProgressPanel
        v-if="store.isReplaying && !store.jobStatus"
        :isReplaying="true"
      />
    </div>

    <PaymentModal v-if="store.showPayment" @paid="handlePaid" />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import * as api from '../services/api.js'
import TaskList from '../components/TaskList.vue'
import ProgressPanel from '../components/ProgressPanel.vue'
import PaymentModal from '../components/PaymentModal.vue'

const router = useRouter()
const store = useAppStore()
const loading = ref(false)
const retrying = ref(false)
const wsRef = ref(null)
const contactEmail = ref('')

const finalMessage = computed(() => {
  return store.jobStatus?.progress?.message || store.progressData?.message || '本轮任务处理结束，但仍有任务未确认完成'
})
const doneMessage = computed(() => store.jobStatus?.progress?.message || '全部任务已完成')
const finalTitle = computed(() => {
  if (store.jobStatus?.status === 'failed') return '任务执行失败'
  if (store.jobStatus?.status === 'stopped') return '任务已停止'
  return '部分任务未完成'
})
const remainingCount = computed(() => store.tasks.length || store.jobStatus?.result?.verify?.incomplete || 0)

onMounted(() => {
  if (!store.isLoggedIn) {
    router.push('/')
    return
  }
  api.trackVisit(store.sessionId, '/dashboard')
  loadContact()
  fetchProgress()
})

async function loadContact() {
  try {
    const res = await api.getPublicConfig()
    if (res.data.contact_email) contactEmail.value = res.data.contact_email
  } catch (e) {
    // 客服信息拉取失败不影响主流程
  }
}

onUnmounted(() => {
  closeJobWebSocket()
})

watch(() => store.jobStatus, (job) => {
  if (job && (job.status === 'running' || job.status === 'pending')) {
    if (!store.wsConnected && !store.isReplaying) {
      connectJobWebSocket()
    }
  }
})

async function fetchProgress() {
  loading.value = true
  try {
    const res = await api.getProgress(store.sessionId)
    store.setTasks(res.data.tasks)
    store.courseTotalTasks = res.data.total_tasks || 0
    store.setUserInfo({
      nickname: res.data.nickname,
      user_id: res.data.user_id,
      cookie: '', sesskey: '',
    })
    if (res.data.job) {
      store.setJobStatus(res.data.job)
    }
  } catch (e) {
    if (e.response?.status === 401) {
      store.reset()
      router.push('/')
    }
  } finally {
    loading.value = false
  }
}

function connectJobWebSocket() {
  // 已有存活连接时不重复建连，避免重连风暴 / 多个 socket 推送同一进度
  if (wsRef.value && (wsRef.value.readyState === WebSocket.OPEN || wsRef.value.readyState === WebSocket.CONNECTING)) {
    return
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/progress/${store.sessionId}`
  const ws = new WebSocket(wsUrl)
  wsRef.value = ws
  ws.onopen = () => { store.wsConnected = true; store.setReplaying(true) }
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'progress') store.updateProgress(data)
    else if (data.type === 'error') store.setReplaying(false)
    else if (data.type === 'phase') {
      store.updateProgress(data)
      if (data.visit_progress || data.replay_progress || data.mark_progress) {
        const j = store.jobStatus || {}
        store.setJobStatus({ ...j,
          visit_progress: data.visit_progress || j.visit_progress,
          replay_progress: data.replay_progress || j.replay_progress,
          mark_progress: data.mark_progress || j.mark_progress,
        })
      }
    } else if (data.type === 'finished') {
      store.setReplaying(false)
      store.updateProgress(data.progress || { message: data.message || '' })
      store.setJobStatus({
        ...(store.jobStatus || {}),
        status: data.status || 'done',
        phase: data.phase || store.jobStatus?.phase,
        progress: data.progress || { ...(store.jobStatus?.progress || {}), message: data.message || '' },
        visit_progress: data.visit_progress || store.jobStatus?.visit_progress,
        replay_progress: data.replay_progress || store.jobStatus?.replay_progress,
        mark_progress: data.mark_progress || store.jobStatus?.mark_progress,
        result: data.result || store.jobStatus?.result,
      })
      closeJobWebSocket()
      fetchProgress()
    }
  }
  ws.onclose = () => { store.wsConnected = false; if (wsRef.value === ws) wsRef.value = null }
  ws.onerror = () => { store.wsConnected = false }
}

function closeJobWebSocket() {
  const ws = wsRef.value
  if (!ws) return
  wsRef.value = null
  // 解绑回调后再关闭，避免 onclose 触发额外状态变更
  ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null
  try { ws.close() } catch (e) {}
  store.wsConnected = false
}

function handleLogout() {
  closeJobWebSocket()
  api.logout(store.sessionId)
  store.reset()
  router.push('/')
}

function handleStartPayment() {
  if (store.validCount === 0) return
  store.replayError = ''
  store.setPayment('')
}

function handlePaid() {
  store.closePayment()
  fetchProgress()
}

async function handleRetry() {
  retrying.value = true
  store.replayError = ''
  try {
    const res = await api.retryTasks(store.sessionId)
    if (res.data.job) store.setJobStatus(res.data.job)
    if (Array.isArray(res.data.tasks)) store.setTasks(res.data.tasks)
    if (res.data.started) {
      store.setReplaying(true)
      connectJobWebSocket()
    } else {
      await fetchProgress()
    }
  } catch (e) {
    store.replayError = e.response?.data?.detail || '重试启动失败，请稍后再试'
  } finally {
    retrying.value = false
  }
}

function goAdmin() { router.push('/admin') }
</script>
