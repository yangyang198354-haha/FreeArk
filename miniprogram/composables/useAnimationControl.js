/**
 * @module MOD-BD-003
 * @implements IFC-BD-003-01, IFC-BD-003-02, IFC-BD-003-03, IFC-BD-003-04, IFC-BD-003-05
 * @depends none
 * @author sub_agent_software_developer
 * @description Controls CSS animation pause/resume based on page visibility.
 *   Exposes a reactive `animationsPaused` boolean.
 *   Page binds it as :class="{ 'animations-paused': animationsPaused }" on the root element.
 *   CSS rule: .animations-paused * { animation-play-state: paused !important; }
 */
import { ref } from 'vue'

export function useAnimationControl() {
  const animationsPaused = ref(false)

  /** IFC-BD-003-02: Pause all CSS animations. */
  function pause() {
    animationsPaused.value = true
  }

  /** IFC-BD-003-03: Resume all CSS animations. */
  function resume() {
    animationsPaused.value = false
  }

  /** IFC-BD-003-04: Called from page onShow. */
  function onShow() {
    resume()
  }

  /** IFC-BD-003-05: Called from page onHide. */
  function onHide() {
    pause()
  }

  return {
    /** IFC-BD-003-01 */
    animationsPaused,
    pause,
    resume,
    onShow,
    onHide,
  }
}
