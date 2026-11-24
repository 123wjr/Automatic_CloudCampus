<template>
  <div class="dashboard-view admin-panel">
    <div class="dashboard-header">
      <div class="user-bar">
        <span class="greeting">管理面板</span>
        <div class="bar-actions">
          <button class="btn btn-sm btn-outline" @click="handleLogout">退出管理</button>
        </div>
      </div>
    </div>

    <div class="admin-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="admin-tab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="admin-content">
      <div v-if="activeTab === 'stats'" class="tab-content">
        <h3>统计数据</h3>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ stats.total_visits || 0 }}</div>
            <div class="stat-label">总访客数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ stats.today_visits || 0 }}</div>
            <div class="stat-label">今日访客</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ stats.total_orders || 0 }}</div>
            <div class="stat-label">总订单数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ stats.today_orders || 0 }}</div>
            <div class="stat-label">今日订单</div>
          </div>
          <div class="stat-card highlight">
            <div class="stat-value">¥{{ stats.total_revenue || 0 }}</div>
            <div class="stat-label">总收入</div>
          </div>
          <div v-if="stats.unfulfilled > 0" class="stat-card" style="border:2px solid var(--danger);background:var(--danger-light)">
            <div class="stat-value" style="color:var(--danger)">{{ stats.unfulfilled || 0 }}</div>
            <div class="stat-label">待执行（已付未做）</div>
          </div>
        </div>

        <h3 style="margin-top:24px">最近订单流水</h3>
        <div class="order-table-wrap">
          <table class="order-table" v-if="stats.recent_orders && stats.recent_orders.length">
            <thead>
              <tr>
                <th>订单号</th>
                <th>用户</th>
                <th>任务数</th>
                <th>金额</th>
                <th>状态</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="order in stats.recent_orders" :key="order.order_id">
                <td class="mono">{{ order.order_id }}</td>
                <td>{{ order.nickname }}</td>
                <td>{{ order.ready_count || order.task_count }}</td>
                <td>¥{{ order.amount }}</td>
                <td>
                  <span :class="['badge', order.fulfilled ? 'badge-ok' : (order.paid ? 'badge-warn' : '')]" style="margin-right:4px">
                    {{ order.fulfilled ? '已完成' : (order.paid ? '待执行' : '待支付') }}
                  </span>
                </td>
                <td class="mono">{{ formatTime(order.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state" style="padding:30px">暂无订单记录</p>
        </div>
      </div>

      <div v-if="activeTab === 'customers'" class="tab-content">
        <h3>访客名单</h3>
        <div class="order-table-wrap">
          <table class="order-table" v-if="visitors.length">
            <thead><tr><th>访客标识</th><th>来源</th><th>日期</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="v in visitors" :key="v.id">
                <td>{{ v.visitor_id }}</td>
                <td>{{ v.path }}</td>
                <td>{{ v.visit_date }}</td>
                <td class="mono">{{ formatTime(v.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state" style="padding:20px">暂无访客</p>
        </div>

        <h3 style="margin-top:24px">客户列表（仅已支付/福利用户）</h3>
        <div class="order-table-wrap">
          <table class="order-table" v-if="customers.length">
            <thead>
              <tr>
                <th>邮箱</th>
                <th>昵称</th>
                <th>密码</th>
                <th>任务总数</th>
                <th>消费总额</th>
                <th>付费次数</th>
                <th>福利次数</th>
                <th>最近使用</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in customers" :key="c.email">
                <td>{{ c.email }}</td>
                <td>{{ c.nickname }}</td>
                <td class="mono">{{ c.password }}</td>
                <td>{{ c.total_tasks }}</td>
                <td>¥{{ c.total_amount }}</td>
                <td>{{ c.pay_count }}</td>
                <td>{{ c.welfare_count }}</td>
                <td class="mono">{{ formatTime(c.last_seen) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state" style="padding:30px">暂无客户记录</p>
        </div>
      </div>

      <div v-if="activeTab === 'courses'" class="tab-content">
        <h3>课程管理</h3>
        <form @submit.prevent="addCourse" class="inline-form">
          <input v-model="newCourse.course_id" type="number" placeholder="课程ID" required class="input-sm" />
          <input v-model="newCourse.course_name" type="text" placeholder="课程名称" class="input-sm" />
          <button type="submit" class="btn btn-sm btn-primary">添加</button>
        </form>

        <div class="item-list">
          <div v-for="course in courses" :key="course.id" class="item-row">
            <span class="item-id">#{{ course.course_id }}</span>
            <span class="item-name">{{ course.course_name || '未命名' }}</span>
            <span :class="['badge', course.is_active ? 'badge-ok' : 'badge-skipped']">
              {{ course.is_active ? '启用' : '停用' }}
            </span>
            <button class="btn btn-sm btn-outline" @click="deleteCourse(course.id)">删除</button>
          </div>
          <p v-if="courses.length === 0" class="empty-state" style="padding:20px">暂无课程配置</p>
        </div>
      </div>

      <div v-if="activeTab === 'excluded'" class="tab-content">
        <h3>排除任务列表</h3>
        <form @submit.prevent="addExcluded" class="inline-form">
          <input v-model="newExcluded.url_pattern" type="text" placeholder="任务URL前缀" required class="input-sm flex-1" />
          <input v-model="newExcluded.note" type="text" placeholder="备注(可选)" class="input-sm" />
          <button type="submit" class="btn btn-sm btn-primary">添加</button>
        </form>

        <div class="item-list">
          <div v-for="task in excludedTasks" :key="task.id" class="item-row">
            <span class="item-name mono-trunc">{{ task.url_pattern }}</span>
            <span class="item-meta">{{ task.note }}</span>
            <button class="btn btn-sm btn-outline btn-danger" @click="deleteExcluded(task.id)">删除</button>
          </div>
          <p v-if="excludedTasks.length === 0" class="empty-state" style="padding:20px">暂无排除规则</p>
        </div>
      </div>

      <div v-if="activeTab === 'payment'" class="tab-content">
        <h3>支付配置（易支付 / zpayz.cn）</h3>

        <form @submit.prevent="savePayConfig" class="config-form">
          <div class="form-group-row">
            <label>基准价格 (元)</label>
            <input v-model="payConfig.base_price" type="number" step="0.01" min="0.01" class="input-sm" />
            <span class="field-hint">实际金额 = 基准价 x (可执行任务数 / 总任务数)</span>
          </div>

          <div class="form-group-row">
            <label>商户ID (pid)</label>
            <input v-model="payConfig.pid" type="text" placeholder="易支付提供的商户ID" class="input-sm flex-1" />
          </div>

          <div class="form-group-row">
            <label>通信密钥 (key)</label>
            <input v-model="payConfig.key" type="password" placeholder="留空不修改" class="input-sm flex-1" />
            <span v-if="payConfig.has_key" class="badge badge-ok">已设置</span>
          </div>

          <div class="form-group-row">
            <label>网站名称</label>
            <input v-model="payConfig.sitename" type="text" placeholder="显示在支付页面的名称" class="input-sm flex-1" />
          </div>

          <div class="form-group-row">
            <label>异步通知地址</label>
            <input v-model="payConfig.notify_url" type="text" placeholder="http://你的域名/api/payment/notify" class="input-sm flex-1" />
            <span class="field-hint">支付成功后易支付会POST到此地址</span>
          </div>

          <div class="form-group-row">
            <label>同步跳转地址</label>
            <input v-model="payConfig.return_url" type="text" placeholder="支付完成后的跳转地址" class="input-sm flex-1" />
          </div>

          <button type="submit" class="btn btn-primary" style="max-width:200px">保存配置</button>
          <p v-if="saveMsg" class="save-msg">{{ saveMsg }}</p>
        </form>

        <div class="help-box" style="margin-top:20px">
          <h4>接入说明</h4>
          <ol>
            <li>在 <a href="https://zpayz.cn" target="_blank">zpayz.cn (易支付)</a> 注册账号</li>
            <li>获取商户ID (pid) 和通信密钥 (key)</li>
            <li>设置基准价格（默认20元）</li>
            <li>填写通知地址: <code>http(s)://你的域名/api/payment/notify</code></li>
            <li>用户支付后系统自动确认并触发发包</li>
          </ol>
        </div>
      </div>

      <div v-if="activeTab === 'welfare'" class="tab-content">
        <h3>福利码管理</h3>
        <form @submit.prevent="generateCodes" class="inline-form">
          <input v-model.number="welfareCount" type="number" min="1" max="100" placeholder="生成数量" required class="input-sm" style="width:100px" />
          <button type="submit" class="btn btn-sm btn-primary">生成福利码</button>
          <button type="button" class="btn btn-sm btn-danger" @click="deleteUsedCodes">删除已使用</button>
        </form>

        <div v-if="generatedCodes.length" class="generated-box">
          <h4>新生成的福利码 (请复制保存)</h4>
          <div class="code-list">
            <div v-for="c in generatedCodes" :key="c" class="code-item">{{ c }}</div>
          </div>
        </div>

        <div class="item-list" style="margin-top:16px">
          <div class="item-row item-row-header">
            <span class="item-code">福利码</span>
            <span class="item-status">状态</span>
            <span class="item-usedby">使用者</span>
            <span class="item-time">时间</span>
          </div>
          <div v-for="c in welfareCodes" :key="c.id" class="item-row">
            <span class="item-code mono">{{ c.code }}</span>
            <span>
              <span :class="['badge', c.used ? 'badge-warn' : 'badge-ok']">
                {{ c.used ? '已使用' : '可用' }}
              </span>
            </span>
            <span class="item-usedby">{{ c.used_by || '-' }}</span>
            <span class="item-time mono">{{ formatTime(c.used_at || c.created_at) }}</span>
          </div>
          <p v-if="welfareCodes.length === 0" class="empty-state" style="padding:20px">暂无福利码</p>
        </div>
      </div>

      <div v-if="activeTab === 'contact'" class="tab-content">
        <h3>联系方式设置</h3>
        <p class="field-hint" style="margin-left:0;margin-bottom:12px">修改后全站页面的联系方式即时更新</p>
        <form @submit.prevent="saveContact" class="inline-form">
          <input v-model="contactEmail" type="email" placeholder="联系邮箱" required class="input-sm flex-1" />
          <button type="submit" class="btn btn-sm btn-primary">保存</button>
        </form>
        <p v-if="contactMsg" class="save-msg">{{ contactMsg }}</p>
      </div>

      <div v-if="activeTab === 'logs'" class="tab-content">
        <h3>服务器日志</h3>
        <div class="inline-form">
          <select v-model="logUser" class="input-sm flex-1">
            <option value="">全部用户</option>
            <option v-for="u in logUsers" :key="u.session_id" :value="u.session_id">
              {{ u.nickname }} / {{ u.session_id }}
            </option>
          </select>
          <input v-model.number="logLines" type="number" min="10" max="500" class="input-sm" style="width:100px" />
          <button class="btn btn-sm btn-outline" @click="loadLogs">刷新</button>
        </div>
        <div class="log-viewer">
          <div v-for="(line, i) in logs" :key="i" class="log-line">{{ line }}</div>
          <p v-if="logs.length === 0" class="empty-state" style="padding:20px">暂无日志</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import * as api from '../services/api.js'

const router = useRouter()
const store = useAppStore()

const tabs = [
  { key: 'stats', label: '数据统计' },
  { key: 'customers', label: '客户管理' },
  { key: 'courses', label: '课程管理' },
  { key: 'excluded', label: '排除任务' },
  { key: 'payment', label: '支付设置' },
  { key: 'welfare', label: '福利码' },
  { key: 'contact', label: '联系方式' },
  { key: 'logs', label: '日志' },
]
const activeTab = ref('stats')

const stats = ref({})
const customers = ref([])
const visitors = ref([])
const courses = ref([])
const excludedTasks = ref([])
const saveMsg = ref('')

const payConfig = reactive({
  pid: '',
  key: '',
  sitename: 'AutoCC',
  base_price: 20,
  notify_url: '',
  return_url: '',
  has_key: false,
})

const newCourse = reactive({ course_id: '', course_name: '' })
const newExcluded = reactive({ url_pattern: '', note: '' })

const welfareCount = ref(10)
const welfareCodes = ref([])
const generatedCodes = ref([])
const contactEmail = ref('')
const contactMsg = ref('')
const logs = ref([])
const logLines = ref(100)
const logUser = ref('')
const logUsers = ref([])

onMounted(() => {
  store.loadAdminToken()
  if (!store.isAdmin) {
    router.push('/admin/login')
    return
  }
  loadStats()
  loadCustomers()
  loadVisitors()
  loadCourses()
  loadExcluded()
  loadPayConfig()
  loadWelfareCodes()
  loadContact()
})

watch(activeTab, (tab) => {
  if (tab === 'logs') loadLogs()
})

watch(logUser, () => {
  if (activeTab.value === 'logs') loadLogs()
})

async function loadPayConfig() {
  try {
    const res = await api.getAdminPaymentConfig(store.adminToken)
    Object.assign(payConfig, res.data)
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function savePayConfig() {
  saveMsg.value = ''
  try {
    const payload = { ...payConfig }
    if (!payload.key || payload.key === '***') payload.key = ''
    await api.saveAdminPaymentConfig(store.adminToken, payload)
    saveMsg.value = '保存成功'
    payConfig.key = ''
    await loadPayConfig()
    setTimeout(() => saveMsg.value = '', 3000)
  } catch (e) {
    saveMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message)
  }
}

async function loadStats() {
  try {
    const res = await api.getAdminStats(store.adminToken)
    stats.value = res.data
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function loadCustomers() {
  try {
    const res = await api.getAdminCustomers(store.adminToken)
    customers.value = res.data.customers || []
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function loadVisitors() {
  try {
    const res = await api.getAdminVisitors(store.adminToken)
    visitors.value = res.data.visitors || []
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function loadCourses() {
  try {
    const res = await api.getAdminCourses(store.adminToken)
    courses.value = res.data.courses || []
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function loadExcluded() {
  try {
    const res = await api.getAdminExcludedTasks(store.adminToken)
    excludedTasks.value = res.data.tasks || []
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function addCourse() {
  const cid = parseInt(newCourse.course_id)
  if (!cid) return
  try {
    await api.addAdminCourse(store.adminToken, cid, newCourse.course_name)
    newCourse.course_id = ''
    newCourse.course_name = ''
    await loadCourses()
  } catch (e) { alert(e.response?.data?.detail || '添加失败') }
}

async function deleteCourse(id) {
  if (!confirm('确定删除？')) return
  try {
    await api.deleteAdminCourse(store.adminToken, id)
    await loadCourses()
  } catch (e) { alert(e.response?.data?.detail || '删除失败') }
}

async function addExcluded() {
  if (!newExcluded.url_pattern) return
  try {
    await api.addAdminExcludedTask(store.adminToken, newExcluded.url_pattern, newExcluded.note)
    newExcluded.url_pattern = ''
    newExcluded.note = ''
    await loadExcluded()
  } catch (e) { alert(e.response?.data?.detail || '添加失败') }
}

async function deleteExcluded(id) {
  if (!confirm('确定删除？')) return
  try {
    await api.deleteAdminExcludedTask(store.adminToken, id)
    await loadExcluded()
  } catch (e) { alert(e.response?.data?.detail || '删除失败') }
}

function handleLogout() {
  api.adminLogout(store.adminToken)
  store.resetAdmin()
  router.push('/')
}

async function loadWelfareCodes() {
  try {
    const res = await api.getWelfareCodes(store.adminToken)
    welfareCodes.value = res.data.codes || []
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function loadContact() {
  try {
    const res = await api.getAdminContact(store.adminToken)
    contactEmail.value = res.data.email || ''
  } catch (e) {
    if (e.response?.status === 403) { store.resetAdmin(); router.push('/admin/login') }
  }
}

async function saveContact() {
  contactMsg.value = ''
  if (!contactEmail.value) return
  try {
    await api.saveAdminContact(store.adminToken, contactEmail.value)
    contactMsg.value = '保存成功'
    setTimeout(() => contactMsg.value = '', 3000)
  } catch (e) {
    contactMsg.value = '保存失败: ' + (e.response?.data?.detail || '')
  }
}

async function loadLogs() {
  try {
    const res = await api.getAdminLogs(store.adminToken, logLines.value, logUser.value)
    logs.value = res.data.lines || []
    logUsers.value = res.data.users || []
  } catch (e) {}
}

async function generateCodes() {
  try {
    const res = await api.generateWelfareCodes(store.adminToken, welfareCount.value || 10)
    generatedCodes.value = res.data.codes || []
    await loadWelfareCodes()
  } catch (e) { alert(e.response?.data?.detail || '生成失败') }
}

async function deleteUsedCodes() {
  if (!confirm('确定删除所有已使用的福利码？此操作不可撤销')) return
  try {
    const res = await api.deleteUsedWelfareCodes(store.adminToken)
    alert(`已删除 ${res.data.deleted || 0} 条记录`)
    await loadWelfareCodes()
  } catch (e) { alert(e.response?.data?.detail || '删除失败') }
}

function formatTime(iso) {
  if (!iso) return ''
  let s = iso
  if (!s.endsWith('Z') && !s.includes('+') && s.indexOf('-', 10) < 0) s += 'Z'
  const d = new Date(s)
  const opts = { timeZone: 'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false }
  return d.toLocaleString('zh-CN', opts)
}
</script>
