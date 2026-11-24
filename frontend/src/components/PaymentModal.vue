<template>
  <div class="modal-overlay" @click.self="handleClose">
    <div class="modal-card">
      <h3>{{ paid || store.freeMode ? "确认完毕" : "确认支付" }}</h3>

      <!-- Step 1: choose payment method -->
      <template v-if="!paymentMethod && !paid && !store.freeMode">
        <p>
          📋 可执行任务: <strong>{{ store.validCount }}</strong> 个
        </p>
        <p v-if="orderError" class="error-msg">{{ orderError }}</p>
        <div class="modal-actions">
          <button class="btn btn-primary" @click="paymentMethod = 'alipay'">💰 支付宝支付</button>
          <button class="btn btn-primary" @click="paymentMethod = 'welfare'">🎁 福利码支付</button>
          <button class="btn btn-outline" @click="handleClose">取消</button>
        </div>
      </template>

      <!-- Alipay: create order -->
      <template v-else-if="paymentMethod === 'alipay' && !orderId && !paid">
        <p>
          📋 可执行任务: <strong>{{ store.validCount }}</strong> 个
        </p>
        <p v-if="orderError" class="error-msg">{{ orderError }}</p>
        <div class="modal-actions">
          <button class="btn btn-primary" :disabled="creating" @click="createOrder">
            <span v-if="creating" class="btn-spinner"></span>
            {{ creating ? "生成中..." : "生成支付订单" }}
          </button>
          <button class="btn btn-outline" @click="paymentMethod = ''">返回</button>
          <button class="btn btn-outline" @click="handleClose">取消</button>
        </div>
      </template>

      <!-- Alipay: payment in progress -->
      <template v-else-if="paymentMethod === 'alipay' && orderId && !paid">
        <p class="amount-text">💰 金额: ¥{{ amount }}</p>
        <p v-if="basePrice > 0" class="price-formula">
          基准价 ¥{{ basePrice }} × ({{ store.validCount }} / {{ totalTasks }})
          = ¥{{ amount }}
        </p>

        <div v-if="payUrl" class="pay-actions">
          <div v-if="isMobile" class="pay-link-wrap">
            <p>点击下方按钮前往支付宝支付</p>
            <a :href="payUrl" target="_self" class="btn btn-primary pay-btn">
              📱 前往支付宝支付
            </a>
          </div>
          <div v-else class="qr-placeholder">
            <img :src="displayQrUrl" alt="支付宝支付二维码" class="qr-image" />
            <p class="qr-hint">📷 请使用支付宝扫描二维码支付</p>
          </div>
        </div>

        <div class="polling-status">
          <span class="spinner"></span>
          支付完成后将自动开始，无需手动确认…
        </div>

        <p class="payment-safe-note">
          🔒 支付由支付宝官方处理，我们不留存您的支付信息
        </p>

        <p class="poll-fallback">
          已完成支付但页面无反应？
          <a href="#" @click.prevent="recheckNow">点此手动刷新</a>
        </p>
      </template>

      <!-- Welfare: input + validate -->
      <template v-else-if="paymentMethod === 'welfare' && !store.freeMode">
        <p>
          📋 可执行任务: <strong>{{ store.validCount }}</strong> 个
        </p>

        <div class="welfare-section">
          <div class="welfare-row">
            <input
              v-model="welfareCode"
              type="text"
              placeholder="🎁 输入福利码免费执行"
              class="input-sm flex-1"
            />
            <button
              class="btn btn-sm btn-primary"
              style="width: auto"
              @click="redeemWelfare"
            >
              验证
            </button>
          </div>
          <p v-if="welfareError" class="welfare-err">{{ welfareError }}</p>
          <p v-if="welfareOk" class="welfare-ok">{{ welfareOk }}</p>
        </div>

        <div class="modal-actions">
          <button class="btn btn-outline" @click="paymentMethod = ''">返回</button>
          <button class="btn btn-outline" @click="handleClose">取消</button>
        </div>
      </template>

      <!-- Paid (alipay success) -->
      <template v-else-if="paid">
        <div class="paid-success">支付确认成功</div>
        <p>即将开始自动发包 {{ store.validCount }} 个任务</p>
        <div class="modal-actions">
          <button class="btn btn-primary" @click="handleStartReplay">
            开始发包
          </button>
        </div>
      </template>

      <!-- Free mode (welfare validated) -->
      <template v-else-if="store.freeMode">
        <p>{{ welfareOk || "福利码已验证，无需再次支付" }}</p>
        <div class="modal-actions">
          <button class="btn btn-primary" @click="handleStartReplay">
            开始刷题
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from "vue";
import { useAppStore } from "../stores/app.js";
import * as api from "../services/api.js";

const emit = defineEmits(["paid"]);
const store = useAppStore();

const orderId = ref("");
const payUrl = ref("");
const qrBase64 = ref("");
const amount = ref(0);
const basePrice = ref(0);
const totalTasks = ref(store.courseTotalTasks || store.validCount);
const configured = ref(true);
const paid = ref(false);
const polling = ref(false);
const creating = ref(false);
const orderError = ref("");
const freeMode = computed({
  get: () => store.freeMode,
  set: (v) => (store.freeMode = v),
});
const paymentMethod = ref(""); // '' | 'alipay' | 'welfare'
const welfareCode = ref(store.freeCode || "");
const welfareError = ref("");
const welfareOk = ref(store.freeMode ? "福利码已验证，无需再次支付" : "");
let pollTimer = null;
let wsRef = null;

const isMobile = computed(() =>
  /Android|iPhone|iPad|iPod/i.test(navigator.userAgent),
);

const displayQrUrl = computed(() => {
  if (!qrBase64.value) return "";
  return `data:image/png;base64,${qrBase64.value}`;
});

async function redeemWelfare() {
  welfareError.value = "";
  welfareOk.value = "";
  if (!welfareCode.value) {
    welfareError.value = "请输入福利码";
    return;
  }
  try {
    const res = await api.redeemWelfare(
      welfareCode.value,
      store.sessionId,
      store.nickname,
      store.tasks.length,
      store.validCount,
    );
    if (res.data.success) {
      welfareOk.value = res.data.message;
      store.freeMode = true;
      store.freeCode = welfareCode.value;
    }
  } catch (e) {
    welfareError.value = e.response?.data?.detail || "该福利码暂不可用，可联系客服获取新码";
  }
}

async function createOrder() {
  orderError.value = "";
  creating.value = true;
  totalTasks.value = store.courseTotalTasks || store.validCount;
  try {
    const res = await api.createPayment(
      store.sessionId,
      store.nickname,
      store.tasks.length,
      store.validCount,
      totalTasks.value,
      0,
      store.validTasks,
    );
    orderId.value = res.data.order_id;
    amount.value = res.data.amount;
    basePrice.value = res.data.base_price || 0;
    payUrl.value = res.data.pay_url || "";
    qrBase64.value = res.data.qr_base64 || "";
    configured.value = res.data.configured !== false;

    if (payUrl.value && isMobile.value) {
      window.open(payUrl.value, "_self");
    }
    // 生成订单后自动开始轮询，无需用户手动点“确认支付完成”
    startPolling();
  } catch (e) {
    orderError.value =
      e.response?.data?.detail || "下单暂未成功，请稍后重试或联系客服";
  } finally {
    creating.value = false;
  }
}

function startPolling() {
  if (polling.value) return;
  polling.value = true;
  pollTimer = setInterval(checkPaymentOnce, 2000);
}

async function checkPaymentOnce() {
  try {
    const res = await api.checkPaymentStatus(orderId.value);
    if (res.data.paid) {
      paid.value = true;
      polling.value = false;
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      emit("paid");
    }
  } catch (e) {
    // 单次轮询失败忽略，下一次继续
  }
}

// 用户已支付但自动轮询尚未捕获时，提供一次立即查询的兜底入口
function recheckNow() {
  checkPaymentOnce();
}

function handleClose() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  store.closePayment();
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
  // 重放进行中时不关闭 WS — 它由 handleStartReplay 创建, 需要存活到 job 结束
  if (wsRef && !store.isReplaying) {
    wsRef.onopen = wsRef.onmessage = wsRef.onclose = wsRef.onerror = null;
    try { wsRef.close(); } catch (e) {}
    wsRef = null;
  }
});

function handleStartReplay() {
  store.replayError = "";
  store.setReplaying(true);
  store.closePayment();
  connectWebSocket();
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/progress/${store.sessionId}`;
  const ws = new WebSocket(wsUrl);
  wsRef = ws;

  ws.onopen = () => {
    store.wsConnected = true;
    ws.send(
      JSON.stringify({
        type: "start_replay",
        tasks: store.validTasks,
        course_id: 11881,
      }),
    );
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "progress") {
      store.updateProgress(data);
    } else if (data.type === "error") {
      store.setReplaying(false);
      store.replayError = data.message || "任务执行遇到了一点问题，请联系客服协助处理";
    } else if (data.type === "phase") {
      store.updateProgress(data);
      if (data.visit_progress || data.replay_progress || data.mark_progress) {
        const j = store.jobStatus || {};
        store.setJobStatus({
          ...j,
          visit_progress: data.visit_progress || j.visit_progress,
          replay_progress: data.replay_progress || j.replay_progress,
          mark_progress: data.mark_progress || j.mark_progress,
        });
      }
    } else if (data.type === "finished") {
      store.updateProgress(data.progress || { message: data.message, current: 0, total: 0 });
      store.setJobStatus({
        ...(store.jobStatus || {}),
        status: data.status || "done",
        phase: data.phase || store.jobStatus?.phase,
        progress: data.progress || { ...(store.jobStatus?.progress || {}), message: data.message || "" },
        visit_progress: data.visit_progress || store.jobStatus?.visit_progress,
        replay_progress: data.replay_progress || store.jobStatus?.replay_progress,
        mark_progress: data.mark_progress || store.jobStatus?.mark_progress,
        result: data.result || store.jobStatus?.result,
      });
      store.setReplaying(false);
      ws.close();
    }
  };

  ws.onclose = () => {
    store.wsConnected = false;
    if (!store.isReplaying) store.setReplaying(false);
  };

  ws.onerror = () => {
    store.wsConnected = false;
    store.setReplaying(false);
    store.replayError = "网络连接异常，请刷新页面后重试";
  };
}
</script>
