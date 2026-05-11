import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    let detail = error.response?.data?.detail
    if (Array.isArray(detail)) {
      detail = detail.map(d => d.msg || JSON.stringify(d)).join('; ')
    }
    const message = detail || error.message || '请求失败'
    return Promise.reject(new Error(message))
  }
)

export default api
