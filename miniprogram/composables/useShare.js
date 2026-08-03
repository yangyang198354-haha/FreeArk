/**
 * @module MOD-SHARE
 * @description 统一转发卡片。
 *
 *   微信规则：页面必须定义 onShareAppMessage，右上角「…」里的「转发」才可点，
 *   否则置灰 —— 这是转发按钮变灰的唯一原因，与审核、类目、配置项均无关。
 *
 *   所有页面一律转发到 /pages/home/index，理由：
 *   - 落地路径不带 query，避免把 session_key（副官会话）、specific_part（房号）
 *     这类身份相关参数随卡片扩散给接收方；
 *   - 接收方多半未登录，home 的 onLoad/onShow 守卫会 reLaunch 到登录页
 *     （home/index.vue:314、532），落地不会白屏或报错。
 *
 *   未设 imageUrl：项目内无图片资源（图标全是 SVG data-URI），
 *   留空时微信会自动截取页面顶部 5:4 区域作封面。若日后要固定封面，
 *   在此补 imageUrl 即可，一处改动全局生效。
 */
import { onShareAppMessage } from '@dcloudio/uni-app'

const SHARE_PATH = '/pages/home/index'
const SHARE_TITLE = '智能方舟座舱'

/**
 * 在页面 setup 中调用即可点亮「转发」。
 * @param {string} [title] 覆盖默认卡片标题
 */
export function useShare(title) {
  onShareAppMessage(() => ({
    title: title || SHARE_TITLE,
    path: SHARE_PATH,
  }))
}
