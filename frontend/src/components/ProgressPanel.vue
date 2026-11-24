<template>
  <div class="progress-panel" :class="{ done: isComplete, warning: isAttention }">
    <div class="progress-header">
      <span class="progress-icon">{{ statusIcon }}</span>
      <span class="progress-title">{{ panelTitle }}</span>
    </div>

    <div class="dual-progress">
      <div class="phase-section">
        <div class="phase-label">
          📖 阅读页面
          <span v-if="finished || vDone" class="phase-check">✅</span>
        </div>
        <div class="progress-bar-container">
          <div class="progress-bar-fill" :style="{ width: ((finished || vDone) ? 100 : vPct) + '%' }" :class="{ done: finished || vDone }"></div>
        </div>
        <div class="phase-text">{{ phaseText(vCur, vTotal, vDone) }}</div>
      </div>

      <div class="phase-section">
        <div class="phase-label">
          🚀 完成任务
          <span v-if="finished || rDone" class="phase-check">✅</span>
        </div>
        <div class="progress-bar-container">
          <div class="progress-bar-fill" :style="{ width: ((finished || rDone) ? 100 : rPct) + '%' }" :class="{ done: finished || rDone }"></div>
        </div>
        <div class="phase-text">{{ phaseText(rCur, rTotal, rDone) }}</div>
      </div>

      <div v-if="mTotal" class="phase-section">
        <div class="phase-label">
          📝 手动处理
          <span v-if="finished || mDone" class="phase-check">✅</span>
        </div>
        <div class="progress-bar-container">
          <div class="progress-bar-fill" :style="{ width: ((finished || mDone) ? 100 : mPct) + '%' }" :class="{ done: finished || mDone }"></div>
        </div>
        <div class="phase-text">{{ phaseText(mCur, mTotal, mDone) }}</div>
      </div>
    </div>

    <div v-if="msg" class="progress-msg">{{ msg }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAppStore } from '../stores/app.js'

const props = defineProps({
  isReplaying: { type: Boolean, default: false },
  message: { type: String, default: '' },
  progress: { type: Object, default: null },
})

const store = useAppStore()
const jobStatus = computed(() => store.jobStatus?.status || '')
const isActive = computed(() => props.isReplaying || store.isReplaying)
const isComplete = computed(() => !isActive.value && jobStatus.value === 'done')
const isAttention = computed(() => !isActive.value && ['partial', 'failed', 'stopped'].includes(jobStatus.value))
const finished = computed(() => isComplete.value)
const statusIcon = computed(() => {
  if (isActive.value) return '⏳'
  if (isComplete.value) return '✅'
  if (isAttention.value) return '⚠️'
  return '✅'
})
const panelTitle = computed(() => {
  if (isActive.value) return '执行中'
  if (isComplete.value) return props.message || '任务完成'
  if (jobStatus.value === 'partial') return props.message || '部分任务未完成'
  if (jobStatus.value === 'failed') return props.message || '任务执行失败'
  if (jobStatus.value === 'stopped') return props.message || '任务已停止'
  return props.message || '任务结束'
})

const vCur = ref(0)
const vTotal = ref(0)
const vDone = ref(false)
const rCur = ref(0)
const rTotal = ref(0)
const rDone = ref(false)
const mCur = ref(0)
const mTotal = ref(0)
const mDone = ref(false)

const vPct = computed(() => vTotal.value ? Math.round(vCur.value / vTotal.value * 100) : 0)
const rPct = computed(() => rTotal.value ? Math.round(rCur.value / rTotal.value * 100) : 0)
const mPct = computed(() => mTotal.value ? Math.round(mCur.value / mTotal.value * 100) : 0)
const msg = computed(() => (props.progress || store.progressData).message || '')

// 阶段文本：阶段已完成(done)或整体结束(finished)即视为完成 ——
// 有总数时显示 总数/总数，无总数（如无阅读任务）时显示“已完成”；
// 否则进行中显示 当前/总数，未开始显示“等待中...”。
function phaseText(cur, total, done) {
  const complete = done || finished.value
  if (total) return (complete ? total : cur) + '/' + total
  return complete ? '已完成' : '等待中...'
}

// Initialize from job status (reconnect case)
watch(() => store.jobStatus, (j) => {
  if (!j) return
  if (j.visit_progress) {
    vCur.value = j.visit_progress.current || 0
    vTotal.value = j.visit_progress.total || 0
    vDone.value = j.visit_progress.done || false
  }
  if (j.replay_progress) {
    rCur.value = j.replay_progress.current || 0
    rTotal.value = j.replay_progress.total || 0
    rDone.value = j.replay_progress.done || false
  }
  if (j.mark_progress) {
    mCur.value = j.mark_progress.current || 0
    mTotal.value = j.mark_progress.total || 0
    mDone.value = j.mark_progress.done || false
  }
}, { immediate: true })

// Watch for live progress updates
watch(() => props.progress || store.progressData, (p) => {
  if (!p) return
  const msg = p.message || ''
  const cur = p.current || 0
  const tot = p.total || 0
  const phase = p.phase || ''

  // 完成判定用 current 抵达 total，而不是匹配消息里的“完成”——
  // 每条逐任务消息（如“正在标记 X 为已完成…”）都含“完成”，会让进度条一上来就满。
  if (phase === 'visit' || msg.includes('阅读') || msg.includes('访问') || msg.includes('visiting')) {
    vCur.value = cur
    if (tot) vTotal.value = tot
    if (tot && cur >= tot) vDone.value = true
  } else if (phase === 'replay' || msg.includes('发包') || msg.includes('处理') || msg.includes('success')) {
    // 仅在有真实进度(tot>0)时才把前序阶段标记完成；否则像启动时
    // “开始回放”这种零进度的 replay 信号会让阅读条提前变满。
    if (tot) vDone.value = true
    rCur.value = cur
    if (tot) rTotal.value = tot
    if (tot && cur >= tot) rDone.value = true
  } else if (phase === 'mark' || msg.includes('手动') || msg.includes('点击任务')) {
    if (tot) { vDone.value = true; rDone.value = true }
    mCur.value = cur
    if (tot) mTotal.value = tot
    if (tot && cur >= tot) mDone.value = true
  }
}, { deep: true })
</script>
