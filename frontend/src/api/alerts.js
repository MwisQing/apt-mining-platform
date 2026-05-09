import api from './index'

export function fetchAlerts(params) {
  return api.get('/api/alerts', { params })
}

export function fetchAlertOptions(params) {
  return api.get('/api/alerts/options', { params })
}

export function annotateAlert(alertId, data) {
  return api.patch(`/api/alerts/${alertId}/annotation`, data)
}

export async function exportAlerts(params) {
  const resp = await api.post('/api/alerts/export', null, {
    params,
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(new Blob([resp]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', `alerts_export.xlsx`)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
