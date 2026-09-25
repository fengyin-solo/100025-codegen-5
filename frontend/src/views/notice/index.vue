<template>
  <section class="page" data-module="notice">
    <header class="page-head">
      <div>
        <h2>拍摄通告管理</h2>
        <p class="page-desc">维护拍摄通告单，围绕通告编号、拍摄日期、集合时间、拍摄地点做登记、筛选与状态流转；支持按拍摄日批量下发。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记拍摄通告单</button>
        <button class="btn primary" type="button" @click="openBatchPanel">批量下发通告</button>
        <button class="btn" type="button" @click="exportRows">导出拍摄通告清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>通告编号</span>
        <input v-model="filters.keyword" placeholder="按通告编号检索" />
      </label>
      <label class="filter-item">
        <span>通告状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>批次编号</span>
        <input v-model="filters.batch_no" placeholder="按批次编号查看" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button
              v-if="column === '批次编号' && row['批次编号']"
              class="link"
              type="button"
              @click="viewBatch(String(row['批次编号']))"
            >
              {{ row['批次编号'] }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无拍摄通告数据，可先登记或批量下发拍摄通告单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条拍摄通告记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="batchPanelOpen" class="modal-mask" @click.self="closeBatchPanel">
      <div class="modal-dialog">
        <header class="modal-head">
          <h3>拍摄通告批量下发</h3>
          <button class="link" type="button" @click="closeBatchPanel">关闭</button>
        </header>
        <p class="modal-tip">
          勾选多个拍摄日逐条生成通告单；集合时间、拍摄地点、出勤人员按条校验，整组中失败项不影响成功项。
          当前批次号：<strong>{{ batchNo }}</strong>
        </p>

        <div v-if="batchLoading" class="modal-loading">正在读取拍摄日清单…</div>

        <template v-else>
          <section class="batch-section">
            <h4>① 选择拍摄日</h4>
            <div class="day-picker">
              <label v-for="day in shootingDays" :key="String(day.id)" class="day-chip">
                <input
                  type="checkbox"
                  :checked="isDaySelected(day)"
                  @change="toggleDay(day, ($event.target as HTMLInputElement).checked)"
                />
                <span>{{ day['拍摄日编号'] }}｜{{ day['拍摄日期'] }}｜{{ day['拍摄地点'] }}</span>
              </label>
              <span v-if="!shootingDays.length" class="empty-state">暂无可选拍摄日</span>
            </div>
          </section>

          <section class="batch-section">
            <h4>② 逐条核对通告信息（{{ batchItems.length }} 条）</h4>
            <table v-if="batchItems.length" class="data-table batch-table">
              <thead>
                <tr>
                  <th>拍摄日编号</th>
                  <th>拍摄日期</th>
                  <th>集合时间</th>
                  <th>拍摄地点</th>
                  <th>出勤人员</th>
                  <th>拍摄场次</th>
                  <th>用车安排</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in batchItems" :key="item.client_key">
                  <td>{{ item['拍摄日编号'] }}</td>
                  <td>{{ item['拍摄日期'] }}</td>
                  <td><input v-model="item['集合时间']" placeholder="HH:MM" /></td>
                  <td><input v-model="item['拍摄地点']" placeholder="拍摄地点" /></td>
                  <td><input v-model="item['出勤人员']" placeholder="多人用顿号分隔" /></td>
                  <td><input v-model="item['拍摄场次']" placeholder="选填" /></td>
                  <td><input v-model="item['用车安排']" placeholder="选填" /></td>
                  <td><button class="link" type="button" @click="removeItem(item)">移除</button></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="empty-state">尚未选择拍摄日</p>
          </section>

          <section v-if="batchResult" class="batch-section">
            <h4>
              ③ 下发结果：成功 {{ batchResult.success_count }} 条 / 失败 {{ batchResult.failure_count }} 条
            </h4>
            <p :class="batchResult.failure_count ? 'result-warn' : 'result-ok'">{{ batchResult.message }}</p>
            <ul class="result-list">
              <li v-for="result in batchResult.results" :key="result.client_key" :class="result.ok ? 'result-ok' : 'result-fail'">
                <span class="result-flag">{{ result.ok ? '成功' : '失败' }}</span>
                <span class="result-key">{{ result.client_key }}（{{ result['拍摄日期'] }}）</span>
                <span v-if="result.ok" class="result-detail">通告编号 {{ result['通告编号'] }}，集合 {{ result['集合时间'] }}，地点 {{ result['拍摄地点'] }}</span>
                <span v-else class="result-detail">{{ result.message }}</span>
              </li>
            </ul>
          </section>

          <p v-if="batchError" class="error-text">{{ batchError }}</p>

          <footer class="modal-foot">
            <button class="btn" type="button" :disabled="batchSubmitting" @click="closeBatchPanel">取消</button>
            <button
              v-if="batchResult && batchResult.failure_count > 0"
              class="btn primary"
              type="button"
              :disabled="batchSubmitting"
              @click="retryFailed"
            >
              {{ batchSubmitting ? '重试中…' : `仅重试失败项（${batchResult.failure_count} 条）` }}
            </button>
            <button
              v-else-if="!batchResult"
              class="btn primary"
              type="button"
              :disabled="batchSubmitting || !batchItems.length"
              @click="submitBatch"
            >
              {{ batchSubmitting ? '下发中…' : `批量下发（${batchItems.length} 条）` }}
            </button>
            <button
              v-if="batchResult"
              class="btn"
              type="button"
              :disabled="batchSubmitting"
              @click="viewByBatch"
            >
              返回列表并按本批查看
            </button>
          </footer>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface BatchItem {
  client_key: string
  拍摄日编号: string
  拍摄日期: string
  集合时间: string
  拍摄地点: string
  出勤人员: string
  拍摄场次: string
  用车安排: string
}

interface BatchResultItem {
  ok: boolean
  client_key: string
  拍摄日期?: string
  集合时间?: string
  拍摄地点?: string
  出勤人员?: string
  message: string
  entry_id: number | null
  通告编号: string | null
  submitted?: Record<string, unknown>
}

interface BatchResult {
  batch_no: string
  total: number
  success_count: number
  failure_count: number
  message?: string
  results: BatchResultItem[]
}

const ENDPOINT = '/api/notice'
const columns = ["通告编号", "拍摄日期", "集合时间", "拍摄地点", "拍摄场次", "出勤人员", "用车安排", "通告状态", "批次编号"]
const actions = ["下发通告", "开始执行", "确认完成"]
const statuses = ["待下发", "已下发", "执行中", "已完成"]
const stats = [{"label": "今日通告", "value": 0}, {"label": "待下发通告", "value": 0}, {"label": "未完成通告", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string; batch_no: string }>({
  keyword: '',
  status: '',
  batch_no: '',
})

const batchPanelOpen = ref(false)
const batchLoading = ref(false)
const batchSubmitting = ref(false)
const batchError = ref('')
const batchNo = ref('')
const shootingDays = ref<Row[]>([])
const batchItems = ref<BatchItem[]>([])
const batchResult = ref<BatchResult | null>(null)

function resetFilters() {
  filters.value = { keyword: '', status: '', batch_no: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '拍摄通告单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('拍摄通告动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!payload.ok) {
      throw new Error(payload.message ?? '拍摄通告动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '拍摄通告操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) query.set('status', filters.value.status)
  if (filters.value.batch_no) query.set('batch_no', filters.value.batch_no.trim())
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('拍摄通告单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '拍摄通告列表读取失败'
  }
}

// ----------------------------------------------------------------------
// 批量下发
// ----------------------------------------------------------------------
function makeBatchNo() {
  const stamp = Date.now().toString(36).toUpperCase()
  return `BAT-NOTI-WEB-${stamp}`
}

async function openBatchPanel() {
  batchPanelOpen.value = true
  batchLoading.value = true
  batchError.value = ''
  batchResult.value = null
  batchItems.value = []
  if (!batchNo.value) {
    batchNo.value = makeBatchNo()
  }
  try {
    const response = await request('/api/shooting?size=200')
    if (!response.ok) {
      throw new Error('拍摄日清单读取失败')
    }
    const payload = await response.json()
    shootingDays.value = payload.items ?? []
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '拍摄日清单读取失败'
    shootingDays.value = []
  } finally {
    batchLoading.value = false
  }
}

function closeBatchPanel() {
  batchPanelOpen.value = false
  batchError.value = ''
}

function isDaySelected(day: Row) {
  const key = String(day['拍摄日编号'] ?? '')
  return batchItems.value.some((item) => item.client_key === key)
}

function toggleDay(day: Row, checked: boolean) {
  const key = String(day['拍摄日编号'] ?? '')
  if (checked) {
    if (batchItems.value.some((item) => item.client_key === key)) {
      return
    }
    batchItems.value.push({
      client_key: key,
      拍摄日编号: key,
      拍摄日期: String(day['拍摄日期'] ?? ''),
      集合时间: '07:00',
      拍摄地点: String(day['拍摄地点'] ?? ''),
      出勤人员: '',
      拍摄场次: '',
      用车安排: '',
    })
  } else {
    batchItems.value = batchItems.value.filter((item) => item.client_key !== key)
  }
  batchResult.value = null
}

function removeItem(item: BatchItem) {
  batchItems.value = batchItems.value.filter((candidate) => candidate.client_key !== item.client_key)
  batchResult.value = null
}

function payloadOfItems(items: BatchItem[]) {
  return items.map((item) => ({
    client_key: item.client_key,
    拍摄日编号: item.拍摄日编号,
    拍摄日期: item.拍摄日期,
    集合时间: item.集合时间,
    拍摄地点: item.拍摄地点,
    出勤人员: item.出勤人员,
    拍摄场次: item.拍摄场次,
    用车安排: item.用车安排,
  }))
}

async function submitBatch() {
  batchError.value = ''
  batchSubmitting.value = true
  try {
    const response = await request(`${ENDPOINT}/batch`, {
      method: 'POST',
      body: JSON.stringify({ batch_no: batchNo.value, items: payloadOfItems(batchItems.value) }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '批量下发未生效，请稍后重试')
    }
    batchResult.value = payload as BatchResult
    // 同一 batch_no 重提时后端回放原结果，不影响后续仅重试失败项。
    batchNo.value = payload.batch_no
    await reload()
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '批量下发失败'
  } finally {
    batchSubmitting.value = false
  }
}

function failedItemsFromResult(result: BatchResult): BatchItem[] {
  const currentByKey = new Map(batchItems.value.map((item) => [item.client_key, item]))
  return result.results
    .filter((item) => !item.ok)
    .map((item) => {
      const current = currentByKey.get(item.client_key)
      if (current) {
        return current
      }
      const submitted = (item.submitted ?? {}) as Partial<BatchItem>
      return {
        client_key: item.client_key,
        拍摄日编号: String(submitted.拍摄日编号 ?? ''),
        拍摄日期: String(submitted.拍摄日期 ?? item.拍摄日期 ?? ''),
        集合时间: String(submitted.集合时间 ?? item.集合时间 ?? ''),
        拍摄地点: String(submitted.拍摄地点 ?? item.拍摄地点 ?? ''),
        出勤人员: String(submitted.出勤人员 ?? item.出勤人员 ?? ''),
        拍摄场次: String(submitted.拍摄场次 ?? ''),
        用车安排: String(submitted.用车安排 ?? ''),
      }
    })
}

async function retryFailed() {
  if (!batchResult.value) {
    return
  }
  batchError.value = ''
  batchSubmitting.value = true
  const failedItems = failedItemsFromResult(batchResult.value)
  // 保留成功项在编辑表中的只读存在感：同步成「成功 + 待重试」全集，重试只发失败项。
  try {
    const response = await request(`${ENDPOINT}/batch/${batchResult.value.batch_no}/retry`, {
      method: 'POST',
      body: JSON.stringify({ items: payloadOfItems(failedItems) }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '失败通告重试未生效，请稍后重试')
    }
    batchResult.value = payload as BatchResult
    batchNo.value = payload.batch_no
    await reload()
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '失败通告重试失败'
  } finally {
    batchSubmitting.value = false
  }
}

function hydrateItemsFromResult(result: BatchResult) {
  batchItems.value = result.results.map((item) => {
    const submitted = (item.submitted ?? {}) as Partial<BatchItem>
    return {
      client_key: item.client_key,
      拍摄日编号: String(submitted.拍摄日编号 ?? ''),
      拍摄日期: String(submitted.拍摄日期 ?? item.拍摄日期 ?? ''),
      集合时间: String(submitted.集合时间 ?? item.集合时间 ?? ''),
      拍摄地点: String(submitted.拍摄地点 ?? item.拍摄地点 ?? ''),
      出勤人员: String(submitted.出勤人员 ?? item.出勤人员 ?? ''),
      拍摄场次: String(submitted.拍摄场次 ?? ''),
      用车安排: String(submitted.用车安排 ?? ''),
    }
  })
}

async function viewBatch(no: string) {
  batchPanelOpen.value = true
  batchLoading.value = true
  batchError.value = ''
  batchResult.value = null
  batchItems.value = []
  batchNo.value = no
  try {
    const [noticeResponse, shootingResponse] = await Promise.all([
      request(`${ENDPOINT}/batch/${no}`),
      request('/api/shooting?size=200'),
    ])
    if (!noticeResponse.ok) {
      const payload = await noticeResponse.json().catch(() => ({}))
      throw new Error(payload.detail ?? `批次 ${no} 读取失败`)
    }
    shootingDays.value = shootingResponse.ok
      ? ((await shootingResponse.json()).items ?? [])
      : []
    batchResult.value = (await noticeResponse.json()) as BatchResult
    hydrateItemsFromResult(batchResult.value)
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '批次结果读取失败'
    shootingDays.value = []
  } finally {
    batchLoading.value = false
  }
}

function viewByBatch() {
  if (batchResult.value) {
    filters.value.batch_no = batchResult.value.batch_no
  }
  batchPanelOpen.value = false
  void reload()
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 16px;
  overflow-y: auto;
  z-index: 100;
}
.modal-dialog {
  width: min(1080px, 100%);
  background: #fff;
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 16px 20px;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.2);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-tip { color: var(--muted); font-size: 12px; margin: 8px 0; }
.modal-loading { padding: 24px 0; text-align: center; color: var(--muted); }
.batch-section { margin-top: 12px; }
.batch-section h4 { margin: 0 0 8px; font-size: 13px; }
.day-picker { display: flex; flex-wrap: wrap; gap: 8px; max-height: 140px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
.day-chip { display: flex; align-items: center; gap: 6px; font-size: 12px; border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px; background: #f8fafc; cursor: pointer; }
.batch-table input { width: 100%; border: 1px solid var(--border); border-radius: 4px; padding: 4px 6px; font-size: 12px; }
.result-list { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.result-list li { display: flex; gap: 8px; align-items: baseline; font-size: 12px; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.result-flag { font-weight: 600; flex: none; }
.result-ok { color: #067647; }
.result-fail, .result-warn { color: #b42318; }
.result-key { flex: none; font-weight: 600; }
.result-detail { color: var(--muted); }
.modal-foot { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
