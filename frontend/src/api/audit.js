import api from './index'

export function fetchAuditLogs(params) {
  return api.get('/api/audit-log', { params })
}

export function fetchAuditActions() {
  return api.get('/api/audit-log/actions')
}
