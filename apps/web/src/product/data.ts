import type {
  ActivationKeyRecord,
  AdminUserRecord,
  InterviewTask,
  ReviewRecord,
} from './types'

export const INITIAL_TASKS: InterviewTask[] = [
  {
    id: 'backend-interview',
    name: '后端开发面试',
    createdAt: '2026-08-22 16:30',
    status: 'ready',
    mode: 'interview',
    mobileRequired: true,
  },
  {
    id: 'java-senior-round-one',
    name: 'Java 高级工程师一面',
    createdAt: '2026-08-21 14:20',
    status: 'completed',
    mode: 'interview',
    mobileRequired: true,
  },
  {
    id: 'payment-architecture',
    name: '支付系统架构面试',
    createdAt: '2026-08-18 09:15',
    status: 'completed',
    mode: 'interview',
    mobileRequired: true,
  },
  {
    id: 'redis-practice',
    name: 'Redis 专项模拟',
    createdAt: '2026-08-16 16:45',
    status: 'completed',
    mode: 'practice',
    mobileRequired: false,
  },
]

export const REVIEW_RECORDS: ReviewRecord[] = [
  {
    id: 'review-java',
    taskId: 'java-senior-round-one',
    taskName: 'Java 高级工程师一面',
    date: '2026-08-21 14:20',
    duration: '48 分钟',
    questionCount: 23,
    avgLatency: 2684,
  },
  {
    id: 'review-payment',
    taskId: 'payment-architecture',
    taskName: '支付系统架构面试',
    date: '2026-08-18 09:15',
    duration: '61 分钟',
    questionCount: 28,
    avgLatency: 2812,
  },
  {
    id: 'review-redis',
    taskId: 'redis-practice',
    taskName: 'Redis 专项模拟',
    date: '2026-08-16 16:45',
    duration: '32 分钟',
    questionCount: 16,
    avgLatency: 2416,
  },
]

export const INITIAL_ACTIVATION_KEYS: ActivationKeyRecord[] = [
  {
    id: 'key-1',
    displayKey: 'AB-8N2K-4Q7M-X9FD',
    status: '未使用',
    createdAt: '2026-08-22 09:10',
    expiresAt: '2026-09-22 09:10',
  },
  {
    id: 'key-2',
    displayKey: 'AB-5HT9-P3LR-72KC',
    status: '已使用',
    createdAt: '2026-08-20 13:42',
    expiresAt: '2026-09-20 13:42',
    boundUser: 'zhangsan',
  },
  {
    id: 'key-3',
    displayKey: 'AB-7VQ2-M8WA-1B6E',
    status: '已吊销',
    createdAt: '2026-08-18 16:08',
    expiresAt: '2026-09-18 16:08',
  },
]

export const ADMIN_USERS: AdminUserRecord[] = [
  {
    id: 'user-1',
    name: '张三',
    username: 'zhangsan',
    registeredAt: '2026-08-20',
    taskCount: 4,
    status: '正常',
  },
  {
    id: 'user-2',
    name: '李明',
    username: 'liming',
    registeredAt: '2026-08-19',
    taskCount: 7,
    status: '正常',
  },
  {
    id: 'user-3',
    name: '王倩',
    username: 'wangqian',
    registeredAt: '2026-08-17',
    taskCount: 2,
    status: '已停用',
  },
]

export const REVIEW_TIMELINE = [
  {
    time: '14:31:25',
    type: '面试官',
    title: '你在项目中使用过哪些缓存中间件？',
    detail: 'ASR final · 782ms',
  },
  {
    time: '14:31:32',
    type: '候选人',
    title: '主要使用过 Redis，也接触过本地缓存。',
    detail: 'ASR final · 694ms',
  },
  {
    time: '14:32:01',
    type: 'Focus',
    title: 'Redis 为什么这么快？',
    detail: 'generation 7 · FAST · 1651ms',
  },
  {
    time: '14:32:03',
    type: '建议回答',
    title: '核心：内存访问、单线程命令执行、I/O 多路复用和高效数据结构。',
    detail: 'DeepSeek V4 Flash Vision · 126 tokens',
  },
]
