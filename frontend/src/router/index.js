import { createRouter, createWebHistory } from 'vue-router'
import Workbench from '../views/Workbench.vue'
import AlertList from '../views/AlertList.vue'
import EventManager from '../views/EventManager.vue'
import IocNotes from '../views/IocNotes.vue'
import Settings from '../views/Settings.vue'
import AuditLog from '../views/AuditLog.vue'
import DeviceManager from '../views/DeviceManager.vue'
import AlertAnnotation from '../views/AlertAnnotation.vue'

const routes = [
  { path: '/', component: Workbench, meta: { title: '研判工作台' } },
  { path: '/alerts', component: AlertList, meta: { title: '原始告警' } },
  { path: '/annotations', component: AlertAnnotation, meta: { title: '告警标注' } },
  { path: '/events', component: EventManager, meta: { title: '事件管理' } },
  { path: '/devices', component: DeviceManager, meta: { title: '设备管理' } },
  { path: '/ioc-notes', component: IocNotes, meta: { title: 'IOC 备注' } },
  { path: '/settings', component: Settings, meta: { title: '导入与设置' } },
  { path: '/audit', component: AuditLog, meta: { title: '审计日志' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} - APT Mining Workbench` : 'APT Mining Workbench'
})

export default router
