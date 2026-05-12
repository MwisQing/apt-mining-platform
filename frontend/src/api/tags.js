import api from './index'

export function importTextFiles(files) {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  return api.post('/api/tags/batches/import-text-files', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function fetchBatches(params) {
  return api.get('/api/tags/batches', { params })
}

export function fetchBatch(id) {
  return api.get(`/api/tags/batches/${id}`)
}

export function deleteBatch(id) {
  return api.delete(`/api/tags/batches/${id}`)
}

export function removeDevicesFromBatch(batchId, devices) {
  return api.delete(`/api/tags/batches/${batchId}/devices`, { data: { devices } })
}

export function restoreBatch(batchId) {
  return api.post(`/api/tags/batches/${batchId}/restore`)
}

export function fetchTags() {
  return api.get('/api/tags')
}

export function batchAddDeviceTag(data) {
  return api.post('/api/tags/devices/batch', data)
}

export function batchRemoveDeviceTag(data) {
  return api.delete('/api/tags/devices/batch', { data })
}

export function addDeviceTag(deviceId, data) {
  return api.post('/api/tags/devices/tags', { device_id: deviceId, ...data })
}

export function removeDeviceTag(deviceId, tagId) {
  return api.delete(`/api/tags/devices/${deviceId}/tags/${tagId}`)
}

export function fetchDeviceTags(deviceId) {
  return api.get(`/api/tags/devices/${deviceId}/tags`)
}

export function updateTag(tagId, data) {
  return api.patch(`/api/tags/tags/${tagId}`, data)
}
