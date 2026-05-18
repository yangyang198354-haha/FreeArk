import { onUnmounted } from 'vue'
import mqtt from 'mqtt'

const BROKER_WS_URL = import.meta.env.VITE_MQTT_WS_URL || 'ws://192.168.31.98:32797/mqtt'

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
