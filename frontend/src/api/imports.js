import api, { uploadApi } from './index'

export function uploadExcel(files, onProgress) {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  return uploadApi.post('/api/imports', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress ? (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    } : undefined,
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

export function repairImportMetadata(id) {
  return api.post(`/api/imports/${id}/repair-metadata`)
}

export function deleteAllImports(backup = false) {
  return api.delete('/api/imports/all', { params: { backup } })
}

export function reprocessQueuedImports() {
  return api.post('/api/imports/reprocess-queued')
}
