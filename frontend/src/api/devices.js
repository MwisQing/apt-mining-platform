import api from './index'

export function listDevices(params) {
  return api.get('/api/devices', { params })
}

export function addDeviceTags(deviceId, tags) {
  return api.post(`/api/devices/${deviceId}/tags`, { tags })
}

export function removeDeviceTag(deviceId, tagName) {
  return api.delete(`/api/devices/${deviceId}/tags/${encodeURIComponent(tagName)}`)
}
