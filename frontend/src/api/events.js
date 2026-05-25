import api from './index'

export function fetchEvents(params) {
  return api.get('/api/events', { params })
}

export function fetchEvent(id) {
  return api.get(`/api/events/${id}`)
}

export function createEvent(data) {
  return api.post('/api/events', data)
}

export function updateEvent(id, data) {
  return api.patch(`/api/events/${id}`, data)
}

export function deleteEvent(id) {
  return api.delete(`/api/events/${id}`)
}

export function addFollowup(id, data) {
  return api.post(`/api/events/${id}/followups`, data)
}

export function addDevices(id, data) {
  return api.post(`/api/events/${id}/devices`, data)
}

export function addIocs(id, data) {
  return api.post(`/api/events/${id}/iocs`, data)
}

export function removeDevice(eventId, deviceId) {
  return api.delete(`/api/events/${eventId}/devices/${deviceId}`)
}

export function removeIoc(eventId, target, port) {
  return api.delete(`/api/events/${eventId}/iocs`, { params: { target, port } })
}

export function extractIocs(text) {
  return api.post('/api/events/extract-iocs', { text })
}
