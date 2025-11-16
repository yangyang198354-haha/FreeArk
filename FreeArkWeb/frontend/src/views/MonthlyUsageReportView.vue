<template>
  <div class="monthly-usage-report-container">
    <h2>能耗月用量报表</h2>
    
    <!-- 筛选条件区域 -->
    <div class="filter-section">
      <el-form :inline="true" class="filter-form">
        <el-form-item label="单元">
          <el-input v-model="filterForm.unit" placeholder="请输入单元" style="width: 100px;"></el-input>
        </el-form-item>
        <el-form-item label="楼栋">
          <el-input v-model="filterForm.building" placeholder="请输入楼栋" style="width: 100px;"></el-input>
        </el-form-item>
        <el-form-item label="户号">
          <el-input v-model="filterForm.houseNumber" placeholder="请输入户号" style="width: 100px;"></el-input>
        </el-form-item>
        
        <el-form-item label="供能模式">
          <el-select v-model="filterForm.energyMode" placeholder="请选择" style="width: 150px;">
            <el-option label="制冷" value="制冷"></el-option>
            <el-option label="制热" value="制热"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="能耗周期">
          <el-date-picker
            v-model="filterForm.energyPeriod"
            type="month"
            placeholder="选择月份"
            format="YYYY-MM"
            value-format="YYYY-MM"
            style="width: 150px;">
          </el-date-picker>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="handleQuery">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>
    
    <!-- 数据表格区域 -->
    <div class="table-section">
      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        border
        style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" align="center"></el-table-column>
        <el-table-column prop="specific_part" label="专有部分" width="120" align="center"></el-table-column>
        <el-table-column prop="building" label="楼栋" width="80" align="center"></el-table-column>
        <el-table-column prop="unit" label="单元" width="80" align="center"></el-table-column>
        <el-table-column prop="room_number" label="房号" width="100" align="center"></el-table-column>
        <el-table-column prop="energy_mode" label="功能模式" width="120" align="center"></el-table-column>
        <el-table-column prop="initial_energy" label="初始能量" width="120" align="center"></el-table-column>
        <el-table-column prop="final_energy" label="最终能量" width="120" align="center"></el-table-column>
        <el-table-column prop="usage_quantity" label="能耗用量" width="150" align="center"></el-table-column>
        <el-table-column prop="usage_month" label="能耗周期" width="120" align="center"></el-table-column>
        <!-- 更多列根据实际需求添加 -->
      </el-table>
    </div>
    
    <!-- 分页区域 -->
    <div class="pagination-section">
      <el-pagination
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
        :current-page="currentPage"
        :page-sizes="[10, 20, 50, 100]"
        :page-size="pageSize"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total">
      </el-pagination>
    </div>
  </div>
</template>

<script>
export default {
  name: 'MonthlyUsageReportView',
  data() {
    return {
      filterForm: {
        unit: '',
        building: '',
        houseNumber: '',
        energyMode: '',
        energyPeriod: '' // YYYY-MM format
      },
      tableData: [],
      loading: false,
      currentPage: 1,
      pageSize: 10,
      total: 0
    }
  },
  methods: {
    // 查询数据
    handleQuery() {
      this.loading = true;
      
      // 根据筛选条件从后端API获取数据
      
      const params = {
        unit: this.filterForm.unit,
        building: this.filterForm.building,
        room_number: this.filterForm.houseNumber,
        energy_mode: this.filterForm.energyMode,
        usage_month: this.filterForm.energyPeriod,
        page: this.currentPage,
        size: this.pageSize
      };      
      // 使用axios请求后端接口
      this.$axios.get('/api/usage/quantity/monthly/', { params })
        .then(response => {
          // 处理后端返回的数据
          if (response.data.success) {
            this.tableData = response.data.data;
            this.total = response.data.total;
          } else {
            this.$message.error('获取数据失败');
          }
        })
        .catch(error => {
          console.error('获取数据失败:', error);
          this.$message.error('获取数据失败，请重试');
        })
        .finally(() => {
          this.loading = false;
        });
    },
    
    // 重置筛选条件
    handleReset() {
      this.filterForm = {
        unit: '',
        building: '',
        houseNumber: '',
        functionMode: '',
        energyPeriod: ''
      };
    },
    
    // 分页大小变化
    handleSizeChange(newSize) {
      this.pageSize = newSize;
      this.handleQuery();
    },
    
    // 当前页变化
    handleCurrentChange(newPage) {
      this.currentPage = newPage;
      this.handleQuery();
    }
  },
  mounted() {
    // 页面加载时默认加载当前月份数据
    const now = new Date();
    this.filterForm.energyPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }
}
</script>

<style scoped>
.monthly-usage-report-container {
  padding: 20px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.filter-section {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 8px;
}

.filter-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.table-section {
  margin-bottom: 20px;
}

.pagination-section {
  text-align: right;
}
</style>