<template>
  <section class="page" data-module="notice">
    <header class="page-head">
      <div>
        <h2>拍摄通告管理</h2>
        <p class="page-desc">维护拍摄通告单，围绕通告编号、拍摄日期、集合时间、拍摄地点做登记、筛选与状态流转。</p>
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

    <section v-if="batchPanelOpen" class="batch-panel">
      <h3>批量下发通告</h3>
      <p class="page-desc">
        勾选多个拍摄日，逐条填写集合时间、拍摄地点、出勤人员后一次提交；同一批数据重复提交不会重复创建。
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th>选择</th>
            <th>拍摄日编号</th>
            <th>拍摄日期</th>
            <th>集合时间</th>
            <th>拍摄地点</th>
            <th>出勤人员</th>
            <th>用车安排</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="day in shootingDays" :key="dayKey(day)">
            <td>
              <input
                type="checkbox"
                :checked="Boolean(selectedDays[dayKey(day)])"
                @change="toggleDay(day)"
              />
            </td>
            <td>{{ day.拍摄日编号 }}</td>
            <td>{{ day.拍摄日期 }}</td>
            <td>
              <input
                v-model="batchForm[dayKey(day)].集合时间"
                placeholder="HH:MM"
                :disabled="!selectedDays[dayKey(day)]"
              />
            </td>
            <td>
              <input
                v-model="batchForm[dayKey(day)].拍摄地点"
                placeholder="集合地点"
                :disabled="!selectedDays[dayKey(day)]"
              />
            </td>
            <td>
              <input
                v-model="batchForm[dayKey(day)].出勤人员"
                placeholder="出勤人员"
                :disabled="!selectedDays[dayKey(day)]"
              />
            </td>
            <td>
              <input
                v-model="batchForm[dayKey(day)].用车安排"
                placeholder="选填"
                :disabled="!selectedDays[dayKey(day)]"
              />
            </td>
          </tr>
          <tr v-if="!shootingDays.length">
            <td colspan="7" class="empty-state">暂无拍摄日数据，请先在拍摄进度中登记拍摄日</td>
          </tr>
        </tbody>
      </table>
      <div class="batch-actions">
        <button class="btn primary" type="button" :disabled="batchSubmitting" @click="submitBatch">
          {{ batchSubmitting ? '提交中…' : '提交批量下发' }}
        </button>
        <button class="btn ghost" type="button" @click="batchPanelOpen = false">收起</button>
      </div>

      <div v-if="batchResult" class="batch-result">
        <p :class="batchResult.failed ? 'error-text' : 'ok-text'">{{ batchMessage }}</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>拍摄日编号</th>
              <th>结果</th>
              <th>通告编号</th>
              <th>集合时间</th>
              <th>拍摄地点</th>
              <th>出勤人员</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in batchResult.items ?? []" :key="item.拍摄日编号">
              <td>{{ item.拍摄日编号 }}</td>
              <td>
                <span class="tag" :class="item.ok ? 'ok' : 'fail'">{{ item.ok ? '成功' : '失败' }}</span>
              </td>
              <td>{{ item.通告编号 ?? '—' }}</td>
              <td>
                <input v-if="!item.ok" v-model="item.values.集合时间" placeholder="HH:MM" />
                <template v-else>{{ item.values.集合时间 }}</template>
              </td>
              <td>
                <input v-if="!item.ok" v-model="item.values.拍摄地点" placeholder="集合地点" />
                <template v-else>{{ item.values.拍摄地点 }}</template>
              </td>
              <td>
                <input v-if="!item.ok" v-model="item.values.出勤人员" placeholder="出勤人员" />
                <template v-else>{{ item.values.出勤人员 }}</template>
              </td>
              <td>{{ item.message }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="batchResult.failed" class="batch-actions">
          <button class="btn primary" type="button" :disabled="batchSubmitting" @click="retryFailed">
            {{ batchSubmitting ? '重试中…' : `只重试失败项（${batchResult.failed} 条）` }}
          </button>
        </div>
      </div>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span v-if="batchFilter" class="filter-chip">
        当前按批次 {{ batchFilter }} 查看
        <button class="link" type="button" @click="clearBatchFilter">清除</button>
      </span>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无拍摄通告数据，可先登记拍摄通告单</td>
        </tr>
      </tbody>
    </table>

    <section class="batch-history">
      <h3>下发批次</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>批次号</th>
            <th>提交条数</th>
            <th>成功</th>
            <th>失败</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="batch in batches" :key="batch.批次号">
            <td>{{ batch.批次号 }}</td>
            <td>{{ batch.total }}</td>
            <td>{{ batch.succeeded }}</td>
            <td>{{ batch.failed }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="filterByBatch(batch.批次号)">查看该批通告</button>
              <button class="link" type="button" @click="toggleBatchDetail(batch.批次号)">
                {{ activeBatch?.批次号 === batch.批次号 ? '收起明细' : '查看明细' }}
              </button>
            </td>
          </tr>
          <tr v-if="!batches.length">
            <td colspan="5" class="empty-state">暂无批量下发记录</td>
          </tr>
        </tbody>
      </table>
      <div v-if="activeBatch" class="batch-result">
        <table class="data-table">
          <thead>
            <tr>
              <th>拍摄日编号</th>
              <th>结果</th>
              <th>通告编号</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in activeBatch.items ?? []" :key="item.拍摄日编号">
              <td>{{ item.拍摄日编号 }}</td>
              <td>
                <span class="tag" :class="item.ok ? 'ok' : 'fail'">{{ item.ok ? '成功' : '失败' }}</span>
              </td>
              <td>{{ item.通告编号 ?? '—' }}</td>
              <td>{{ item.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条拍摄通告记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface BatchItem {
  拍摄日编号: string
  ok: boolean
  message: string
  通告编号: string | null
  entry_id: number | null
  values: Record<string, string>
}

interface Batch {
  批次号: string
  total: number
  succeeded: number
  failed: number
  items?: BatchItem[]
}

interface BatchFormRow {
  集合时间: string
  拍摄地点: string
  出勤人员: string
  用车安排: string
}

const ENDPOINT = '/api/notice'
const SHOOTING_ENDPOINT = '/api/shooting'
const columns = ["通告编号", "拍摄日期", "集合时间", "拍摄地点", "拍摄场次", "出勤人员", "用车安排", "通告状态", "批次号"]
const actions = ["下发通告", "开始执行", "确认完成"]
const statuses = ["待下发", "已下发", "执行中", "已完成"]
const stats = [{"label": "今日通告", "value": 0}, {"label": "待下发通告", "value": 0}, {"label": "未完成通告", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const batchFilter = ref('')

const batchPanelOpen = ref(false)
const batchSubmitting = ref(false)
const batchKey = ref('')
const shootingDays = ref<Row[]>([])
const selectedDays = ref<Record<string, boolean>>({})
const batchForm = ref<Record<string, BatchFormRow>>({})
const batchResult = ref<Batch | null>(null)
const batchMessage = ref('')
const batches = ref<Batch[]>([])
const activeBatch = ref<Batch | null>(null)

function dayKey(day: Row): string {
  return String(day.拍摄日编号 ?? '')
}

function resetFilters() {
  filters.value = {}
  batchFilter.value = ''
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
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('拍摄通告动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '拍摄通告操作失败'
  }
}

function toggleDay(day: Row) {
  const key = dayKey(day)
  if (selectedDays.value[key]) {
    delete selectedDays.value[key]
    return
  }
  selectedDays.value[key] = true
  if (!batchForm.value[key]) {
    batchForm.value[key] = {
      集合时间: '',
      拍摄地点: String(day.拍摄地点 ?? ''),
      出勤人员: '',
      用车安排: '',
    }
  }
}

async function openBatchPanel() {
  batchPanelOpen.value = true
  batchResult.value = null
  batchMessage.value = ''
  batchKey.value = crypto.randomUUID()
  if (shootingDays.value.length) {
    return
  }
  try {
    const response = await request(`${SHOOTING_ENDPOINT}?size=200`)
    if (!response.ok) {
      throw new Error('拍摄日列表读取失败')
    }
    const payload = await response.json()
    shootingDays.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '拍摄日列表读取失败'
  }
}

async function submitBatch() {
  const items = Object.keys(selectedDays.value)
    .filter((key) => selectedDays.value[key])
    .map((key) => ({ 拍摄日编号: key, ...batchForm.value[key] }))
  if (!items.length) {
    batchMessage.value = '请先勾选需要下发的拍摄日'
    batchResult.value = null
    return
  }
  batchSubmitting.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batch-dispatch`, {
      method: 'POST',
      body: JSON.stringify({ batch_key: batchKey.value, items }),
    })
    if (!response.ok) {
      throw new Error('批量下发请求未生效，请稍后重试')
    }
    const payload = await response.json()
    batchResult.value = payload.batch
    batchMessage.value = payload.message
    await Promise.all([reload(), loadBatches()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量下发失败'
  } finally {
    batchSubmitting.value = false
  }
}

async function retryFailed() {
  const batch = batchResult.value
  if (!batch) {
    return
  }
  const items = (batch.items ?? [])
    .filter((item) => !item.ok)
    .map((item) => ({ 拍摄日编号: item.拍摄日编号, ...item.values }))
  batchSubmitting.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batches/${batch.批次号}/retry`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
    if (!response.ok) {
      throw new Error('失败项重试未生效，请稍后重试')
    }
    const payload = await response.json()
    batchResult.value = payload.batch
    batchMessage.value = payload.message
    await Promise.all([reload(), loadBatches()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '失败项重试失败'
  } finally {
    batchSubmitting.value = false
  }
}

async function loadBatches() {
  try {
    const response = await request(`${ENDPOINT}/batches`)
    if (!response.ok) {
      throw new Error('下发批次列表读取失败')
    }
    const payload = await response.json()
    batches.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '下发批次列表读取失败'
  }
}

async function toggleBatchDetail(batchNo: string) {
  if (activeBatch.value?.批次号 === batchNo) {
    activeBatch.value = null
    return
  }
  try {
    const response = await request(`${ENDPOINT}/batches/${batchNo}`)
    if (!response.ok) {
      throw new Error('批次明细读取失败')
    }
    activeBatch.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批次明细读取失败'
  }
}

async function filterByBatch(batchNo: string) {
  batchFilter.value = batchNo
  await reload()
}

async function clearBatchFilter() {
  batchFilter.value = ''
  await reload()
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams(filters.value as Record<string, string>)
  if (batchFilter.value) {
    params.set('batch', batchFilter.value)
  }
  const query = params.toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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

onMounted(() => {
  void reload()
  void loadBatches()
})
</script>
