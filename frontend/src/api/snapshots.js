import api from './index'

export function fetchSnapshotStatus() {
  return api.get('/api/snapshots/status')
}

export function rebuildSnapshots() {
  return api.post('/api/snapshots/rebuild')
}
