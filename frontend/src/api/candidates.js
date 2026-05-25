import api from './index'

export function fetchCandidates(params) {
  return api.get('/api/alert-candidates', { params })
}
