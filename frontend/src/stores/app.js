import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sessionId = ref('')
  const nickname = ref('')
  const userId = ref('')
  const userInfo = ref(null)
  const tasks = ref([])
  const courseTotalTasks = ref(0)
  const isLoggedIn = computed(() => !!sessionId.value)
  const showPayment = ref(false)
  const currentOrderId = ref('')
  const isReplaying = ref(false)
  const progressData = ref({ current: 0, total: 0, message: '', title: '' })
  const replayResults = ref([])
  const wsConnected = ref(false)
  const jobStatus = ref(null)
  const replayError = ref('')              // 发包/执行阶段的错误，用页面提示替代 alert
  const freeMode = ref(false)              // 福利码已验证
  const freeCode = ref('')                // 使用的福利码
  const isPaidUser = computed(() => freeMode.value || (jobStatus.value && ['done', 'partial'].includes(jobStatus.value.status)))

  const adminToken = ref('')
  const isAdmin = computed(() => !!adminToken.value)

  const validTasks = computed(() => tasks.value)
  const skippedTasks = computed(() => tasks.value.filter(t => !t.has_packet && !t.excluded))
  const excludedTasks = computed(() => tasks.value.filter(t => t.excluded))
  const validCount = computed(() => validTasks.value.length)
  const skippedCount = computed(() => skippedTasks.value.length)
  const excludedCount = computed(() => excludedTasks.value.length)

  function setSession(data) {
    sessionId.value = data.session_id
    nickname.value = data.nickname
    userId.value = data.user_id
    localStorage.setItem('autocc_session', JSON.stringify({
      session_id: data.session_id,
      nickname: data.nickname,
      user_id: data.user_id,
    }))
  }

  function loadSession() {
    const saved = localStorage.getItem('autocc_session')
    if (saved) {
      try {
        const data = JSON.parse(saved)
        sessionId.value = data.session_id
        nickname.value = data.nickname
        userId.value = data.user_id
        return true
      } catch (e) {}
    }
    return false
  }

  function setUserInfo(info) {
    userInfo.value = info
  }

  function setTasks(list) {
    tasks.value = list
  }

  function setPayment(orderId) {
    showPayment.value = true
    currentOrderId.value = orderId
  }

  function closePayment() {
    showPayment.value = false
  }

  function setReplaying(val) {
    isReplaying.value = val
  }

  function updateProgress(data) {
    progressData.value = { ...progressData.value, ...data }
  }

  function addReplayResult(result) {
    replayResults.value.push(result)
  }

  function setAdminToken(token) {
    adminToken.value = token
    if (token) localStorage.setItem('admin_token', token)
    else localStorage.removeItem('admin_token')
  }

  function loadAdminToken() {
    const saved = localStorage.getItem('admin_token')
    if (saved) adminToken.value = saved
  }

  function setJobStatus(status) {
    jobStatus.value = status
  }

  function reset() {
    sessionId.value = ''
    nickname.value = ''
    userId.value = ''
    userInfo.value = null
    tasks.value = []
    showPayment.value = false
    currentOrderId.value = ''
    isReplaying.value = false
    progressData.value = { current: 0, total: 0, message: '', title: '' }
    replayResults.value = []
    wsConnected.value = false
    jobStatus.value = null
    replayError.value = ''
    freeMode.value = false
    freeCode.value = ''
    localStorage.removeItem('autocc_session')
  }

  function resetAdmin() {
    adminToken.value = ''
    localStorage.removeItem('admin_token')
  }

  return {
    sessionId, nickname, userId, userInfo, tasks, courseTotalTasks, isLoggedIn,
    showPayment, currentOrderId, isReplaying, progressData, replayResults, wsConnected, jobStatus,
    replayError,
    freeMode, freeCode, isPaidUser,
    adminToken, isAdmin,
    validTasks, skippedTasks, excludedTasks, validCount, skippedCount, excludedCount,
    setSession, setUserInfo, setTasks, setPayment, closePayment,
    setReplaying, updateProgress, addReplayResult, reset,
    setAdminToken, loadAdminToken, resetAdmin, setJobStatus, loadSession,
  }
})
