import api from './index'

export function createTraced(data) {
  return api.post('/api/traced', data)
}

export function fetchTracedList(params) {
  return api.get('/api/traced', { params })
}

export function importTraced(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/traced/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function updateTraced(id, data) {
  return api.patch(`/api/traced/${id}`, data)
}

export function deleteTraced(id) {
  return api.delete(`/api/traced/${id}`)
}
