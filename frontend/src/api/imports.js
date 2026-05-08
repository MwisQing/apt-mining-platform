import api from './index'

export function uploadExcel(files) {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  return api.post('/api/imports', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function fetchImports(params) {
  return api.get('/api/imports', { params })
}

export function fetchImport(id) {
  return api.get(`/api/imports/${id}`)
}

export function fetchImportSheets(id) {
  return api.get(`/api/imports/${id}/sheets`)
}

export function fetchImportRows(id, params) {
  return api.get(`/api/imports/${id}/rows`, { params })
}

export function downloadImportRowsCsv(id, type = 'failures') {
  return api.get(`/api/imports/${id}/failures.csv`, {
    params: { type },
    responseType: 'blob',
  })
}

export function deleteImport(id) {
  return api.delete(`/api/imports/${id}`)
}
