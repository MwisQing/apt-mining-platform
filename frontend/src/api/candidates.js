import api from './index'

export function fetchCandidates(params) {
  return api.get('/api/alert-candidates', { params })
}

export function fetchIocDevices(params) {
  return api.get('/api/alert-candidates/ioc-devices', { params })
}
