import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import OrderHistoryView from '../views/OrderHistoryView.vue'
import AdminLogin from '../views/AdminLogin.vue'
import AdminPanel from '../views/AdminPanel.vue'

const routes = [
  { path: '/', name: 'login', component: LoginView },
  { path: '/dashboard', name: 'dashboard', component: DashboardView },
  { path: '/orders', name: 'orders', component: OrderHistoryView },
  { path: '/admin/login', name: 'admin-login', component: AdminLogin },
  { path: '/admin', name: 'admin', component: AdminPanel },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
