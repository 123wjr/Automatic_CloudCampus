<template>
  <div id="app-container">
    <header class="app-header">
      <div class="header-left">
        <span class="app-logo">⚡</span>
        <h1 class="app-title">AutoCC</h1>
        <span class="app-subtitle">云校园任务自动化</span>
      </div>
      <div class="header-right">
        <span class="header-contact">✉️ {{ contactEmail }}</span>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
    <footer class="app-footer">
      <div class="footer-content">
        <p class="footer-text">
          <span class="footer-icon">🛡️</span> 先查询后付费 · 按比例计费 · 完成后自动核对
        </p>
        <p class="footer-contact">
          联系邮箱：{{ contactEmail }}
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

// 占位默认值，真实值由 /api/config/public 下发（后端 CONTACT_EMAIL）
const contactEmail = ref('support@example.com')

onMounted(async () => {
  try {
    const api = await import('./services/api.js')
    const r = await api.getPublicConfig()
    if (r.data.contact_email) contactEmail.value = r.data.contact_email
  } catch (e) {}
})
</script>
