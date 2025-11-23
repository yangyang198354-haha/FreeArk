// API配置文件
// 配置说明：
// - 将useLocal设置为true使用本地开发环境API地址
// - 将useLocal设置为false使用生产环境API地址
// - 修改API地址时直接编辑对应的值

window.API_CONFIG = {
  // 设置为true使用本地环境，false使用生产环境
  useLocal: false,
  
  // 本地开发环境API地址
  localUrl: 'http://localhost',
  
  // 生产环境API地址
  productionUrl: 'http://et116374mm892.vicp.fun',
  
  // 获取当前配置的API基础URL
  get baseUrl() {
    return this.useLocal ? this.localUrl : this.productionUrl;
  }
};

// 打印当前配置信息到控制台，便于调试
console.log('API配置已加载:', {
  environment: window.API_CONFIG.useLocal ? '本地开发环境' : '生产环境',
  baseUrl: window.API_CONFIG.baseUrl
});
