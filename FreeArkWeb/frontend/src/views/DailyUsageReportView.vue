<template>
  <div class="daily-usage-report-container">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span>能耗日用量报表</span>
        </div>
      </template>
      <!-- 在这里添加能耗日用量报表的内容 -->
      <div class="report-content">
        <p>能耗日用量报表内容将在这里显示</p>
      </div>
    </el-card>
  </div>
</template>

<script>
export default {
  name: 'DailyUsageReportView'
}
</script>

<style scoped>
.daily-usage-report-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.report-content {
  margin-top: 20px;
}
</style>