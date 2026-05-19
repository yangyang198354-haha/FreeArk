import { onUnmounted } from 'vue'
import mqtt from 'mqtt'

// v0.4.6 Bug G: 浏览器从公网 vicp.fun 访问，无法直连内网 broker 192.168.31.98:32797。
// 走 nginx 同源反代 /mqtt-ws/ → broker WebSocket，避免跨域 + 公网/内网双兼容。
function _defaultBrokerUrl() {
  if (typeof window === 'undefined') return 'ws://localhost/mqtt-ws/'
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/mqtt-ws/`
}
const BROKER_WS_URL = import.meta.env.VITE_MQTT_WS_URL || _defaultBrokerUrl()

export function useMqttWebSocket(topic, onMessage) {
  let client = null

  function connect() {
    client = mqtt.connect(BROKER_WS_URL, { clean: true })
    client.on('connect', () => {
      client.subscribe(topic, { qos: 1 })
    })
    client.on('message', (receivedTopic, payload) => {
      onMessage({ topic: receivedTopic, payload: payload.toString() })
    })
    client.on('error', (err) => {
      console.error('[useMqttWebSocket] error:', err)
    })
  }

  function disconnect() {
    if (client) {
      client.end()
      client = null
    }
  }

  onUnmounted(disconnect)

  return { connect, disconnect }
}
