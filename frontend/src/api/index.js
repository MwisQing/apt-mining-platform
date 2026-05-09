import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    return Promise.reject(new Error(message))
  }
)

export default api
