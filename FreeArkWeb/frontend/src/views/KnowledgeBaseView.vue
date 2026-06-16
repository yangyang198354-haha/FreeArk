<template>
  <div class="kb-view">
    <!-- 页头 -->
    <div class="kb-page-head">
      <div class="kb-head-accent"></div>
      <div class="kb-head-text">
        <h2 class="kb-head-title">三恒知识库管理</h2>
        <p class="kb-head-sub">上传三恒系统手册、参数表、故障码文档，供知识专家检索作答</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchDocuments" style="margin-left:auto;align-self:center;">刷新</el-button>
    </div>

    <!-- 上传区域 -->
    <el-card class="kb-upload-card" shadow="never">
      <template #header>
        <span class="kb-card-title">上传文档</span>
        <span class="kb-card-hint">仅支持 .docx 和 .pdf，单文件最大 50MB</span>
      </template>
      <el-upload
        class="kb-upload"
        drag
        :auto-upload="false"
        :on-change="handleFileChange"
        :show-file-list="false"
        accept=".docx,.pdf"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">支持 .docx / .pdf，单文件 ≤ 50MB</div>
        </template>
      </el-upload>
      <div v-if="pendingFile" class="kb-pending-file">
        <el-icon><Document /></el-icon>
        <span>{{ pendingFile.name }}</span>
        <span class="kb-file-size">（{{ formatSize(pendingFile.size) }}）</span>
        <el-button type="primary" size="small" :loading="uploading" @click="doUpload">
          确认上传
        </el-button>
        <el-button size="small" @click="pendingFile = null">取消</el-button>
      </div>
    </el-card>

    <!-- 文档列表 -->
    <el-card class="kb-list-card" shadow="never">
      <template #header>
        <span class="kb-card-title">文档列表</span>
        <span class="kb-card-hint">共 {{ documents.length }} 份文档</span>
      </template>
      <el-table
        :data="documents"
        v-loading="loading"
        element-loading-text="加载中..."
        style="width:100%"
        row-key="id"
      >
        <el-table-column label="文件名" prop="file_name" min-width="200" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="上传人" prop="uploaded_by" width="100" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Chunk 数" prop="chunk_count" width="90" />
        <el-table-column label="上传时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed'"
              type="warning"
              size="small"
              @click="openRetryDialog(row)"
            >重试</el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="info"
              size="small"
              @click="showError(row)"
            >查看原因</el-button>
            <el-popconfirm
              title="确认删除该文档及其所有向量数据？"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 失败原因弹窗 -->
    <el-dialog
      v-model="errorDialogVisible"
      title="失败原因"
      width="600px"
    >
      <pre class="kb-error-content">{{ errorDialogContent }}</pre>
      <template #footer>
        <el-button @click="errorDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 重试弹窗（需重新上传文件） -->
    <el-dialog
      v-model="retryDialogVisible"
      title="重试文档入库"
      width="480px"
    >
      <p class="kb-retry-hint">
        原始文件未保存在服务器，重试需重新选择文件：<strong>{{ retryDoc ? retryDoc.file_name : '' }}</strong>
      </p>
      <el-upload
        :auto-upload="false"
        :on-change="handleRetryFileChange"
        :show-file-list="false"
        accept=".docx,.pdf"
      >
        <el-button type="primary">选择文件</el-button>
      </el-upload>
      <div v-if="retryFile" class="kb-pending-file" style="margin-top:12px;">
        <el-icon><Document /></el-icon>
        <span>{{ retryFile.name }}</span>
        <span class="kb-file-size">（{{ formatSize(retryFile.size) }}）</span>
      </div>
      <template #footer>
        <el-button @click="retryDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="retrying"
          :disabled="!retryFile"
          @click="doRetry"
        >确认重试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document, UploadFilled } from '@element-plus/icons-vue'
import axios from 'axios'

// ── 状态 ─────────────────────────────────────────────────────────────────
const documents = ref([])
const loading = ref(false)
const uploading = ref(false)
const pendingFile = ref(null)           // 待上传的文件（File 对象）

const errorDialogVisible = ref(false)
const errorDialogContent = ref('')

const retryDialogVisible = ref(false)
const retryDoc = ref(null)              // 待重试的文档对象
const retryFile = ref(null)             // 重试选择的新文件
const retrying = ref(false)

let pollTimer = null

// ── 常量 ─────────────────────────────────────────────────────────────────
const ALLOWED_EXTS = ['.docx', '.pdf']
const MAX_SIZE = 50 * 1024 * 1024       // 50MB

// ── API helpers ───────────────────────────────────────────────────────────
function getHeaders() {
  const token = localStorage.getItem('userToken')
  return {
    Authorization: `Token ${token}`,
    'X-CSRFToken': getCookie('csrftoken'),
  }
}

function getCookie(name) {
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)')
  return v ? v[2] : ''
}

// ── 文档列表 ──────────────────────────────────────────────────────────────
async function fetchDocuments() {
  loading.value = true
  try {
    const res = await axios.get('/api/rag/documents/', { headers: getHeaders() })
    documents.value = res.data
    // 如有 parsing 状态，启动轮询
    const hasParsing = res.data.some(d => d.status === 'parsing' || d.status === 'pending')
    if (hasParsing) {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (e) {
    ElMessage.error('获取文档列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// ── 文件选择（上传前校验） ────────────────────────────────────────────────
function handleFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!validateFile(file)) return
  pendingFile.value = file
}

function validateFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!ALLOWED_EXTS.includes(ext)) {
    ElMessage.error('仅支持 .docx 和 .pdf 文件')
    return false
  }
  if (file.size > MAX_SIZE) {
    ElMessage.error('文件不能超过 50MB')
    return false
  }
  return true
}

// ── 上传 ─────────────────────────────────────────────────────────────────
async function doUpload() {
  if (!pendingFile.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', pendingFile.value)
    await axios.post('/api/rag/documents/', formData, {
      headers: { ...getHeaders(), 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('上传成功，正在后台解析入库...')
    pendingFile.value = null
    await fetchDocuments()
  } catch (e) {
    const msg = e.response?.data?.error || e.response?.data?.detail || e.message
    ElMessage.error('上传失败: ' + msg)
  } finally {
    uploading.value = false
  }
}

// ── 删除 ─────────────────────────────────────────────────────────────────
async function handleDelete(doc) {
  try {
    await axios.delete(`/api/rag/documents/${doc.id}/`, { headers: getHeaders() })
    ElMessage.success(`已删除文档「${doc.file_name}」`)
    await fetchDocuments()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    ElMessage.error('删除失败: ' + msg)
  }
}

// ── 查看失败原因 ──────────────────────────────────────────────────────────
function showError(doc) {
  errorDialogContent.value = doc.error_message || '（无详细原因）'
  errorDialogVisible.value = true
}

// ── 重试 ─────────────────────────────────────────────────────────────────
function openRetryDialog(doc) {
  retryDoc.value = doc
  retryFile.value = null
  retryDialogVisible.value = true
}

function handleRetryFileChange(uploadFile) {
  const file = uploadFile.raw
  if (!validateFile(file)) return
  retryFile.value = file
}

async function doRetry() {
  if (!retryFile.value || !retryDoc.value) return
  retrying.value = true
  try {
    const formData = new FormData()
    formData.append('file', retryFile.value)
    await axios.post(`/api/rag/documents/${retryDoc.value.id}/retry/`, formData, {
      headers: { ...getHeaders(), 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('重试已触发，后台重新入库中...')
    retryDialogVisible.value = false
    retryFile.value = null
    retryDoc.value = null
    await fetchDocuments()
  } catch (e) {
    const msg = e.response?.data?.error || e.response?.data?.detail || e.message
    ElMessage.error('重试失败: ' + msg)
  } finally {
    retrying.value = false
  }
}

// ── 状态轮询 ──────────────────────────────────────────────────────────────
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(fetchDocuments, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────
function statusTagType(status) {
  const map = { pending: 'info', parsing: 'warning', indexed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { pending: '等待中', parsing: '解析中', indexed: '已入库', failed: '失败' }
  return map[status] || status
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-')
}

// ── 生命周期 ──────────────────────────────────────────────────────────────
onMounted(() => {
  fetchDocuments()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.kb-view {
  padding: 20px 24px;
  min-height: calc(100vh - 60px);
  background: #f5f7fa;
}

.kb-page-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}

.kb-head-accent {
  width: 4px;
  height: 44px;
  background: linear-gradient(180deg, #409EFF, #67C23A);
  border-radius: 2px;
  flex-shrink: 0;
}

.kb-head-title {
  font-size: 18px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 4px 0;
}

.kb-head-sub {
  font-size: 13px;
  color: #8c8c8c;
  margin: 0;
}

.kb-upload-card,
.kb-list-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.kb-card-title {
  font-weight: 600;
  font-size: 14px;
}

.kb-card-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 12px;
}

.kb-upload {
  width: 100%;
}

.kb-pending-file {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 4px;
  font-size: 13px;
}

.kb-file-size {
  color: #909399;
  font-size: 12px;
}

.kb-error-content {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  color: #f56c6c;
  background: #fff5f5;
  padding: 12px;
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.kb-retry-hint {
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
}
</style>
