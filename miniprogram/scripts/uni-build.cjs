// uni-app 3.0 alpha：当 UNI_INPUT_DIR 是相对路径（如 "."）时，uniCopyPlugin 里
// chokidar 用 path.resolve(".") 拼 glob，若 uni CLI 内部 chdir 到别处，"." 解析不到
// 项目根 → static/ 目录不被拷贝，/static/xxx 引用在小程序里 404（"Failed to load image"）。
// 这里把项目根解析为绝对路径后再交给 uni，规避该 bug。用法：
//   node scripts/uni-build.cjs build   # 等价 uni build -p mp-weixin
//   node scripts/uni-build.cjs         # 等价 uni -p mp-weixin（dev/watch）
const { spawnSync } = require('child_process')
const path = require('path')

const root = path.resolve(__dirname, '..')
const uniBin = path.join(root, 'node_modules', '@dcloudio', 'vite-plugin-uni', 'bin', 'uni.js')

const args = [uniBin]
const mode = process.argv[2] // 'build' | 空（dev/watch）
if (mode) args.push(mode)
args.push('-p', 'mp-weixin')

const result = spawnSync(process.execPath, args, {
  stdio: 'inherit',
  env: { ...process.env, UNI_INPUT_DIR: root },
})
process.exit(result.status === null ? 1 : result.status)
