import { createRouter, createWebHistory } from 'vue-router'
import Workbench from '../views/Workbench.vue'
import AlertList from '../views/AlertList.vue'
import EventManager from '../views/EventManager.vue'
import IocNotes from '../views/IocNotes.vue'
import Settings from '../views/Settings.vue'

const routes = [
  { path: '/', component: Workbench },
  { path: '/alerts', component: AlertList },
  { path: '/events', component: EventManager },
  { path: '/ioc-notes', component: IocNotes },
  { path: '/settings', component: Settings },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
