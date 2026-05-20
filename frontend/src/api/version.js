import request from './index'

export function fetchVersion() {
  return request({
    url: '/api/version',
    method: 'get',
  })
}
