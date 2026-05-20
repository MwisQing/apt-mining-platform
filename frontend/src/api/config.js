import api from './index'

export function fetchConfig() {
  return api.get('/api/config')
}

export function saveConfig(data) {
  return api.post('/api/config', data)
}

export function reloadDicts() {
  return api.post('/api/config/reload')
}

export function fetchDicts() {
  return api.get('/api/config/dicts')
}
