<template>
  <div class="usage-query-container">
    <el-card shadow="hover" class="mt-4">
      <template #header>
        <div class="card-header">
          <span>用量数据</span>
        </div>
      </template>
      
      <div v-if="loading" class="loading-container">
        <el-loading-spinner />
        <p>加载中...</p>
      </div>
      
      <div v-else-if="usageData.length === 0" class="no-data-container">
        <el-empty description="暂无数据" />
      </div>
      
      <div v-else class="table-container">
        <el-table :data="usageData" style="width: 100%">
          <el-table-column prop="specific_part" label="专有部分" />
          <el-table-column prop="building" label="楼栋" />
          <el-table-column prop="unit" label="单元" />
          <el-table-column prop="room_number" label="房号" />
          <el-table-column prop="energy_mode" label="供能模式" />
          <el-table-column prop="initial_energy" label="初期能耗(kWh)" />
          <el-table-column prop="final_energy" label="末期能耗(kWh)" />
          <el-table-column prop="usage_quantity" label="使用量(kWh)" />
          <el-table-column prop="time_period" label="时间段" />
        </el-table>
        
        <div class="pagination-container">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import axios from 'axios'

export default {
  name: 'UsageQueryView',
  setup() {
    const usageData = ref([])
    const loading = ref(false)
    const currentPage = ref(1)
    const pageSize = ref(20)
    const total = ref(0)

    // 加载用量数据
    const loadUsageData = async () => {
      loading.value = true
      try {
        const response = await axios.get('/api/usage/quantity/')
        if (response.data && response.data.success) {
          usageData.value = response.data.data
          total.value = response.data.total
        }
      } catch (error) {
        console.error('加载用量数据失败:', error)
      } finally {
        loading.value = false
      }
    }

    // 处理分页大小变化
    const handleSizeChange = (newSize) => {
      pageSize.value = newSize
      // 这里可以添加分页逻辑
    }

    // 处理当前页变化
    const handleCurrentChange = (newCurrent) => {
      currentPage.value = newCurrent
      // 这里可以添加分页逻辑
    }

    onMounted(() => {
      loadUsageData()
    })

    return {
      usageData,
      loading,
      currentPage,
      pageSize,
      total,
      handleSizeChange,
      handleCurrentChange
    }
  }
}
</script>

<style scoped>
.usage-query-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.loading-container {
  text-align: center;
  padding: 40px;
}

.no-data-container {
  text-align: center;
  padding: 40px;
}

.table-container {
  margin-top: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>