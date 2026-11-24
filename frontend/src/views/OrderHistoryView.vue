<template>
  <div class="orders-view">
    <div class="orders-header">
      <div class="user-bar">
        <span class="greeting">📋 {{ store.nickname }} 的订单记录</span>
        <div class="bar-actions">
          <button class="btn btn-sm btn-outline" @click="$router.push('/dashboard')">
            ← 返回仪表盘
          </button>
        </div>
      </div>
    </div>

    <div class="orders-content">
      <div v-if="loading" class="loading">
        <span class="spinner"></span>
        <p>正在加载订单记录...</p>
      </div>

      <div v-else-if="orders.length === 0" class="empty-state">
        <div class="empty-icon">📭</div>
        <p>暂无订单记录</p>
        <p class="empty-sub">支付后订单会自动出现在这里，可作为凭证随时查看</p>
      </div>

      <template v-else>
        <p class="orders-summary">
          共 {{ orders.length }} 条记录，最近 50 条
        </p>

        <div class="order-list">
          <div
            v-for="order in orders"
            :key="order.order_id"
            class="order-item"
          >
            <div class="order-top">
              <span class="order-id" :title="order.order_id">
                #{{ order.order_id.slice(-12) }}
              </span>
              <span
                class="order-status"
                :class="orderStatusClass(order)"
              >
                {{ orderStatusText(order) }}
              </span>
            </div>
            <div class="order-body">
              <div class="order-row">
                <span class="order-label">金额</span>
                <span class="order-value">
                  <template v-if="order.is_welfare">🎁 免费（福利码）</template>
                  <template v-else>¥{{ order.amount }}</template>
                </span>
              </div>
              <div class="order-row">
                <span class="order-label">可执行 / 总计</span>
                <span class="order-value">{{ order.ready_count }} / {{ order.task_count }}</span>
              </div>
              <div class="order-row">
                <span class="order-label">时间</span>
                <span class="order-value">{{ formatTime(order.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <div class="orders-footer-hint">
        <p>💡 订单记录中不包含你的云校园密码，仅保留订单号、金额和任务数量，方便你随时核对</p>
        <p v-if="contactEmail">📮 对订单有疑问？联系客服 {{ contactEmail }}</p>
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

const loading = ref(true)
const orders = ref([])
const contactEmail = ref('')

onMounted(() => {
  if (!store.isLoggedIn) {
    router.push('/')
    return
  }
  loadOrders()
  loadContact()
})

async function loadOrders() {
  try {
    const res = await api.getOrders(store.sessionId)
    orders.value = res.data.orders || []
  } catch (e) {
    orders.value = []
  } finally {
    loading.value = false
  }
}

async function loadContact() {
  try {
    const res = await api.getPublicConfig()
    if (res.data.contact_email) contactEmail.value = res.data.contact_email
  } catch (e) {}
}

function orderStatusClass(order) {
  if (order.fulfilled) return 'status-done'
  if (order.paid) return 'status-paid'
  return 'status-pending'
}

function orderStatusText(order) {
  if (order.fulfilled) return '已完成'
  if (order.is_welfare && order.paid) return '已执行（福利）'
  if (order.paid) return '已支付'
  return '待支付'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>
