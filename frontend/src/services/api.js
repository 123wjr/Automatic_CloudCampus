import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

export function login(account, password) {
  return api.post('/auth/login', { account, password })
}

export function adminLogin(username, password) {
  return api.post('/auth/admin/login', { username, password })
}

export function adminLogout(token) {
  return api.post(`/auth/admin/logout?token=${token}`)
}

export function logout(sessionId) {
  return api.get(`/auth/logout/${sessionId}`)
}

export function getProgress(sessionId, courseId) {
  return api.get(`/tasks/progress/${sessionId}`, { params: { course_id: courseId || 11881 } })
}

export function retryTasks(sessionId, courseId) {
  return api.post(`/tasks/retry/${sessionId}`, null, { params: { course_id: courseId || 11881 } })
}

export function createPayment(userId, nickname, taskCount, readyCount, totalTasks, amount, tasks) {
  return api.post('/payment/create', {
    user_id: userId,
    nickname,
    task_count: taskCount,
    ready_count: readyCount,
    total_tasks: totalTasks || taskCount,
    amount: amount || 0,
    tasks: tasks || [],
  })
}

export function checkPaymentStatus(orderId) {
  return api.get(`/payment/status/${orderId}`)
}

export function getOrders(sessionId) {
  return api.get(`/payment/orders/${sessionId}`)
}

export function simulatePayment(orderId) {
  return api.post(`/payment/simulate/${orderId}`)
}

export function confirmPayment(orderId) {
  return api.post(`/payment/confirm/${orderId}`)
}

export function getCourses(sessionId) {
  return api.get(`/auth/courses/${sessionId}`)
}

export function trackVisit(visitorId, path) {
  return api.post('/admin/track-visit', null, {
    params: { visitor_id: visitorId || 'anonymous', path: path || '/' }
  }).catch(() => {})
}

export function getAdminExcludedTasks(token) {
  return api.get('/admin/excluded-tasks', { params: { token } })
}

export function addAdminExcludedTask(token, urlPattern, note) {
  return api.post('/admin/excluded-tasks', { url_pattern: urlPattern, note }, { params: { token } })
}

export function deleteAdminExcludedTask(token, taskId) {
  return api.delete(`/admin/excluded-tasks/${taskId}`, { params: { token } })
}

export function getAdminCourses(token) {
  return api.get('/admin/courses', { params: { token } })
}

export function addAdminCourse(token, courseId, courseName, isActive) {
  return api.post('/admin/courses', { course_id: courseId, course_name: courseName, is_active: isActive }, { params: { token } })
}

export function deleteAdminCourse(token, courseId) {
  return api.delete(`/admin/courses/${courseId}`, { params: { token } })
}

export function getAdminStats(token) {
  return api.get('/admin/stats', { params: { token } })
}

export function getAdminPaymentConfig(token) {
  return api.get('/admin/payment-config', { params: { token } })
}

export function saveAdminPaymentConfig(token, data) {
  return api.post('/admin/payment-config', data, { params: { token } })
}

export function redeemWelfare(code, userId, nickname, taskCount, readyCount) {
  return api.post('/payment/redeem', null, {
    params: { code, user_id: userId, nickname, task_count: taskCount || 0, ready_count: readyCount || 0 }
  })
}

export function generateWelfareCodes(token, count) {
  return api.post('/admin/welfare-codes/generate', null, {
    params: { token, count: count || 10 }
  })
}

export function getWelfareCodes(token) {
  return api.get('/admin/welfare-codes', { params: { token } })
}

export function deleteUsedWelfareCodes(token) {
  return api.delete('/admin/welfare-codes/used', { params: { token } })
}

export function getPublicConfig() {
  return api.get('/config/public')
}

export function getAdminContact(token) {
  return api.get('/admin/contact', { params: { token } })
}

export function saveAdminContact(token, email) {
  return api.post('/admin/contact', null, { params: { token, email } })
}

export function getAdminCustomers(token) {
  return api.get('/admin/customers', { params: { token } })
}

export function getAdminLogs(token, lines, user) {
  return api.get('/admin/logs', { params: { token, lines: lines || 100, user: user || '' } })
}

export function getAdminVisitors(token) {
  return api.get('/admin/visitors', { params: { token } })
}

export default api
