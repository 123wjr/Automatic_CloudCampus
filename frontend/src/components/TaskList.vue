<template>
  <div class="task-list">
    <div class="task-list-header">
      <span class="col-index">#</span>
      <span class="col-title">任务名称</span>
      <span class="col-status">状态</span>
    </div>
    <div class="task-list-body">
      <div
        v-for="task in tasks"
        :key="task.index"
        class="task-item"
        :class="{
          'has-packet': task.has_packet && !task.excluded,
          'is-mark': !task.has_packet && !task.excluded,
          'is-excluded': task.excluded,
        }"
      >
        <span class="col-index">{{ task.index }}</span>
        <span class="col-title" :title="task.title">{{ task.title }}</span>
        <span class="col-status">
          <span v-if="task.excluded" class="badge badge-excluded">已排除</span>
          <span v-else-if="task.has_packet" class="badge badge-ok">已就绪</span>
          <span v-else class="badge badge-mark">📝 手动处理</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  tasks: { type: Array, required: true },
})
</script>
