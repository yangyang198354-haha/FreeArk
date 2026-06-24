/**
 * @module MOD-POLLER
 * @author sub_agent_software_developer
 * @description Simple interval-based poller for page-level data refresh.
 *   start() calls fn immediately then every intervalMs.
 *   stop() clears the interval (call in onHide / onUnmount).
 */

export class PagePoller {
  constructor(fn, intervalMs = 30000) {
    this._fn = fn
    this._interval = intervalMs
    this._timer = null
  }

  start() {
    this._fn()
    this._timer = setInterval(this._fn, this._interval)
  }

  stop() {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  }
}
