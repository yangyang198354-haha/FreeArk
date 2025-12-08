<template>
  <div class="cascading-selector-container">
    <div class="cascading-selector" style="position: relative;">
      <input 
        type="text" 
        class="cascading-selector-input" 
        placeholder="可直接输入，例:1-2-101"
        v-model="displayValue"
        @input="handleInput"
        @focus="showMenu"
        @click="showMenu"
      >
      <button 
        type="button" 
        class="cascading-clear-btn" 
        :style="{ display: displayValue ? 'block' : 'none', position: 'absolute', right: '5px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#999', fontSize: '16px' }"
        @click="clearSelection"
      >×</button>
      <input type="hidden" :id="buildingInputId" :name="buildingInputName" v-model="selectedBuilding">
      <input type="hidden" :id="unitInputId" :name="unitInputName" v-model="selectedUnit">
      <input type="hidden" :id="roomInputId" :name="roomInputName" v-model="pureRoomNumber">
      <div class="cascading-menu" v-if="isMenuVisible">
        <!-- 搜索结果 -->
        <div v-if="isSearching" class="cascading-search-results">
          <div 
            v-for="(result, index) in searchResults" 
            :key="index"
            class="cascading-menu-item"
            @click="selectSearchResult(result)"
          >
            {{ result.label }}
          </div>
        </div>
        <!-- 级联菜单 -->
        <div v-else class="cascading-menu-content">
          <div 
            v-for="item in menuData" 
            :key="item.value"
            class="cascading-menu-item"
            :class="{ 'has-children': item.children && item.children.length }"
            @click="handleMenuItemClick(item, 0)"
          >
            {{ item.label }}
            <div 
              v-if="item.children && Array.isArray(item.children) && item.children.length > 0" 
              class="cascading-submenu"
              :style="{ display: expandedItems[item.value] ? 'block' : 'none', marginLeft: '20px' }"
            >
              <div 
                v-for="unit in item.children" 
                :key="unit.value"
                class="cascading-menu-item"
                :class="{ 'has-children': unit.children && unit.children.length }"
                @click.stop="handleMenuItemClick(unit, 1, item.value)"
              >
                {{ unit.label }}
                <div 
                v-if="unit.children && Array.isArray(unit.children) && unit.children.length > 0" 
                class="cascading-submenu"
                :style="{ display: expandedItems[`${item.value}-${unit.value}`] ? 'block' : 'none', marginLeft: '20px' }"
              >
                  <div 
                    v-for="room in unit.children" 
                    :key="room.value"
                    class="cascading-menu-item"
                    @click.stop="handleMenuItemClick(room, 2, unit.value, item.value)"
                  >
                    {{ room.label }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import buildingData from '../data/building_data.js'

export default {
  name: 'CascadingSelector',
  props: {
    buildingInputId: {
      type: String,
      default: 'selectedBuilding'
    },
    buildingInputName: {
      type: String,
      default: 'selectedBuilding'
    },
    unitInputId: {
      type: String,
      default: 'selectedUnit'
    },
    unitInputName: {
      type: String,
      default: 'selectedUnit'
    },
    roomInputId: {
      type: String,
      default: 'selectedRoom'
    },
    roomInputName: {
      type: String,
      default: 'selectedRoom'
    }
  },
  data() {
    return {
      displayValue: '',
      selectedBuilding: '',
      selectedUnit: '',
      selectedRoom: '', // 完整的房号value，如"1-1-301"
      pureRoomNumber: '', // 纯房号，如"301"
      buildingData: buildingData || [],
      flattenedBuildingData: [],
      flattenedRooms: [],
      searchResults: [],
      isSearching: false,
      isMenuVisible: false,
      menuData: buildingData || [],
      expandedItems: {}, // 存储展开的菜单项
      parentExpandedItems: {} // 存储父级展开状态
    }
  },
  mounted() {
    // 生成扁平化的建筑数据
    this.generateFlattenedData()
    // 初始化点击外部关闭菜单的事件
    document.addEventListener('click', this.handleClickOutside)
    // 添加窗口大小变化和滚动事件监听
    window.addEventListener('resize', this.updateMenuPosition)
    window.addEventListener('scroll', this.updateMenuPosition)
  },
  beforeUnmount() {
    // 移除事件监听器
    document.removeEventListener('click', this.handleClickOutside)
    window.removeEventListener('resize', this.updateMenuPosition)
    window.removeEventListener('scroll', this.updateMenuPosition)
  },
  methods: {
    // 生成扁平化的建筑数据
    generateFlattenedData() {
      // 生成flattenedBuildingData
      this.flattenedBuildingData = []
      this.flattenedRooms = []
      
      // 检查buildingData是否存在且是数组
      if (!Array.isArray(this.buildingData)) {
        console.error('buildingData is not an array:', this.buildingData)
        return
      }
      
      // 遍历建筑数据
      this.buildingData.forEach(building => {
        // 检查building是否有必要的属性
        if (!building || !building.value || !building.label || !Array.isArray(building.children)) {
          console.error('Invalid building data:', building)
          return
        }
        
        // 添加建筑到扁平化数据
        this.flattenedBuildingData.push({
          value: building.value,
          label: building.label
        })
        
        // 遍历单元数据
        building.children.forEach(unit => {
          // 检查unit是否有必要的属性
          if (!unit || !unit.value || !unit.label || !Array.isArray(unit.children)) {
            console.error('Invalid unit data:', unit)
            return
          }
          
          // 添加单元到扁平化数据
          this.flattenedBuildingData.push({
            value: `${building.value}-${unit.value}`,
            label: `${building.label}${unit.label}`
          })
          
          // 遍历房号数据
          unit.children.forEach(room => {
            // 检查room是否有必要的属性
            if (!room || !room.value || !room.label) {
              console.error('Invalid room data:', room)
              return
            }
            
            // 不解析room.value，直接使用完整格式（如"3-1-702"）
            const fullRoomNumber = room.value;
            
            // 提取纯房号（从fullRoomNumber中提取，如从"3-1-702"中提取"702"）
            let pureRoomNumber = fullRoomNumber;
            if (fullRoomNumber.includes('-')) {
              const parts = fullRoomNumber.split('-');
              if (parts.length >= 3) {
                pureRoomNumber = parts[2];
              }
            }
                  
            // 添加房号到扁平化数据，使用完整的房号作为value
            this.flattenedBuildingData.push({
              value: fullRoomNumber,
              label: `${building.label}${unit.label}${room.label}`
            })
            
            // 添加房号到flattenedRooms数据
            this.flattenedRooms.push({
              building: building.value,
              unit: unit.value,
              room: pureRoomNumber,
              fullValue: fullRoomNumber,
              fullLabel: `${building.label}${unit.label}${room.label}`
            })
          })
        })
      })
    },
    
    // 显示菜单
    showMenu() {
      this.isMenuVisible = true
      this.$nextTick(() => {
        this.updateMenuPosition()
      })
    },
    
    // 更新菜单位置
    updateMenuPosition() {
      const inputEl = this.$el.querySelector('.cascading-selector-input')
      const menuEl = this.$el.querySelector('.cascading-menu')
      
      if (inputEl && menuEl) {
        const rect = inputEl.getBoundingClientRect()
        
        // 设置菜单样式
        menuEl.style.position = 'fixed'
        menuEl.style.top = `${rect.bottom + window.scrollY}px`
        menuEl.style.left = `${rect.left + window.scrollX}px`
        menuEl.style.width = `${rect.width}px`
        menuEl.style.zIndex = '9999'
        menuEl.style.background = 'white'
        menuEl.style.border = '1px solid #ddd'
        menuEl.style.borderRadius = '4px'
        menuEl.style.boxShadow = '0 2px 12px 0 rgba(0, 0, 0, 0.1)'
        menuEl.style.maxHeight = 'calc(100vh - 200px)'
        menuEl.style.overflowY = 'auto'
      }
    },
    
    // 隐藏菜单
    hideMenu() {
      this.isMenuVisible = false
      this.expandedItems = {}
    },
    
    // 处理菜单项点击
    handleMenuItemClick(item, level, parentValue = null, grandparentValue = null) {
      if (item.children && Array.isArray(item.children) && item.children.length > 0) {
        let itemKey = item.value
        // 对于单元级别，使用楼栋-单元作为键，避免不同楼栋的相同单元值冲突
        if (level === 1 && parentValue) {
          itemKey = `${parentValue}-${item.value}`
        }
        // 切换展开状态，使用Object.assign确保响应式更新
        this.expandedItems = Object.assign({}, this.expandedItems, {
          [itemKey]: !this.expandedItems[itemKey]
        })
        if (parentValue) {
          // 确保父级展开
          this.expandedItems = Object.assign({}, this.expandedItems, {
            [parentValue]: true
          })
        }
      } else {
        // 选择房号
        this.selectMenuItem(item, level, parentValue, grandparentValue)
      }
    },
    
    // 选择菜单项
    selectMenuItem(item, level, parentValue = null, grandparentValue = null) {
      const value = item.value
      const label = item.label
      
      // 根据层级确定选择的是楼栋、单元还是户号
      let buildingValue = ''
      let unitValue = ''
      let roomValue = ''
      let pureRoom = ''
      
      // 解析户号级别value格式（楼栋-单元-房号）
      if (level === 2) {
        // 户号级别
        roomValue = value
        
        // 优先使用传递的父级和祖父级值来确保正确性
        if (grandparentValue && parentValue) {
          buildingValue = grandparentValue
          unitValue = parentValue
        } else if (roomValue.includes('-')) {
          // 从value中提取信息作为备选
          const parts = roomValue.split('-')
          if (parts.length >= 3) {
            buildingValue = parts[0]
            unitValue = parts[1]
            pureRoom = parts[2]
          }
        }
        
        // 如果pureRoom还是空的，尝试从item.label提取
        if (!pureRoom) {
          pureRoom = item.label.replace('号', '')
        }
        
        // 最后，确保pureRoom只是房号数字，不是完整的组合值
        if (pureRoom && pureRoom.includes('-')) {
          const parts = pureRoom.split('-')
          if (parts.length >= 3) {
            pureRoom = parts[2]
          }
        }
      } else if (level === 1) {
        // 单元级别
        unitValue = value
        
        // 优先使用传递的父级值来确保正确性
        if (parentValue) {
          buildingValue = parentValue
        } else if (value.includes('-')) {
          const parts = value.split('-')
          if (parts.length >= 2) {
            buildingValue = parts[0]
            unitValue = parts[1]
          }
        } else {
          // 直接使用value作为单元值，从父级获取楼栋值
          const buildingItem = this.menuData.find(building => 
            building.children.some(unit => unit.value === value)
          )
          if (buildingItem) {
            buildingValue = buildingItem.value
            unitValue = value
          }
        }
      } else {
        // 楼栋级别
        buildingValue = value
      }
      
      // 更新选择状态
      this.selectedBuilding = buildingValue
      this.selectedUnit = unitValue
      this.selectedRoom = roomValue
      this.pureRoomNumber = pureRoom
      
      // 更新显示值
      if (roomValue) {
        // 如果选择了房号，显示中文格式：3栋1单元702号
        this.displayValue = `${buildingValue}栋${unitValue}单元${pureRoom}号`
      } else if (buildingValue && unitValue) {
        // 如果选择了单元，显示中文格式：3栋1单元
        this.displayValue = `${buildingValue}栋${unitValue}单元`
      } else if (buildingValue) {
        // 如果选择了楼栋，显示中文格式：3栋
        this.displayValue = `${buildingValue}栋`
      } else {
        this.displayValue = ''
      }
      
      // 关闭菜单
      this.hideMenu()
    },
    
    // 处理输入变化
    handleInput() {
      // 尝试解析输入值，更新选择状态
      const searchTerm = this.displayValue.toLowerCase().trim()
      let building = ''
      let unit = ''
      let room = ''
      let roomValue = ''
      
      // 检查是否为中文格式（如"3栋1单元702号"）
      const chineseFormatMatch = searchTerm.match(/^(\d+)栋(\d+)单元(\d+)号$/)
      if (chineseFormatMatch) {
        [, building, unit, room] = chineseFormatMatch
        roomValue = `${building}-${unit}-${room}`
      } 
      // 检查是否为中文单元格式（如"3栋1单元"）
      else if (searchTerm.match(/^(\d+)栋(\d+)单元$/)) {
        [, building, unit] = searchTerm.match(/^(\d+)栋(\d+)单元$/)
      } 
      // 检查是否为中文楼栋格式（如"3栋"）
      else if (searchTerm.match(/^(\d+)栋$/)) {
        [, building] = searchTerm.match(/^(\d+)栋$/)
      } 
      // 检查是否为数字连接格式（如"3-1-702"）
      else if (searchTerm.match(/^(\d+)-(\d+)-(\d+)$/)) {
        [, building, unit, room] = searchTerm.match(/^(\d+)-(\d+)-(\d+)$/)
        roomValue = searchTerm
      } 
      // 检查是否为数字单元格式（如"3-1"）
      else if (searchTerm.match(/^(\d+)-(\d+)$/)) {
        [, building, unit] = searchTerm.match(/^(\d+)-(\d+)$/)
      }
      
      // 如果匹配到了任何格式，更新选择状态
      if (building) {
        this.selectedBuilding = building
        this.selectedUnit = unit || ''
        this.selectedRoom = roomValue || ''
        this.pureRoomNumber = room || ''
        
        // 执行搜索，支持直接选择
        this.performSearch(searchTerm)
        this.isMenuVisible = true
      } else {
        // 其他格式，执行搜索
        this.performSearch(searchTerm)
        
        // 简单分割处理
        const parts = this.displayValue.split('-')
        if (parts.length === 3) {
          this.selectedBuilding = parts[0]
          this.selectedUnit = parts[1]
          this.selectedRoom = this.displayValue // 使用完整的输入值作为roomValue
          this.pureRoomNumber = parts[2] // 使用纯房号
        } else if (parts.length === 2) {
          this.selectedBuilding = parts[0]
          this.selectedUnit = parts[1]
          this.selectedRoom = ''
          this.pureRoomNumber = ''
        } else if (parts.length === 1) {
          this.selectedBuilding = parts[0]
          this.selectedUnit = ''
          this.selectedRoom = ''
          this.pureRoomNumber = ''
        } else {
          this.selectedBuilding = ''
          this.selectedUnit = ''
          this.selectedRoom = ''
          this.pureRoomNumber = ''
        }
      }
      
      // 如果有搜索内容，显示菜单
      if (searchTerm) {
        this.isMenuVisible = true
      }
    },
    
    // 执行搜索
    performSearch(searchTerm) {
      if (!searchTerm) {
        this.isSearching = false
        this.searchResults = []
        return
      }
      
      // 合并搜索结果
      const results = []
      const term = searchTerm.toLowerCase()
      
      // 1. 从flattenedBuildingData中搜索
      const buildingResults = this.flattenedBuildingData.filter(item => {
        return item.label.toLowerCase().includes(term) || 
               item.value.toLowerCase().includes(term)
      })
      results.push(...buildingResults)
      
      // 2. 从flattenedRooms中搜索更精确的匹配
      const roomResults = this.flattenedRooms.filter(room => {
        // 匹配完整路径或部分路径
        const fullPath = `${room.building}-${room.unit}-${room.room}`
        const buildingUnit = `${room.building}-${room.unit}`
        return fullPath.includes(term) || 
               buildingUnit.includes(term) || 
               room.room.includes(term) || 
               room.fullLabel.toLowerCase().includes(term)
      }).map(room => ({
        value: room.fullValue,
        label: room.fullLabel
      }))
      
      // 添加roomResults到results，去重
      roomResults.forEach(roomResult => {
        if (!results.some(result => result.value === roomResult.value)) {
          results.push(roomResult)
        }
      })
      
      // 3. 处理连字符格式的搜索，如"3-1"或"3-1-702"
      if (term.includes('-')) {
        const parts = term.split('-')
        if (parts.length >= 2) {
          // 至少是building-unit格式
          const building = parts[0]
          const unit = parts[1]
          
          // 从flattenedRooms中查找匹配的房间
          const unitRoomResults = this.flattenedRooms.filter(room => {
            if (parts.length === 2) {
              // 匹配building-unit格式
              return room.building === building && room.unit === unit
            } else {
              // 匹配building-unit-room格式
              return room.building === building && 
                     room.unit === unit && 
                     room.room.includes(parts[2])
            }
          }).map(room => ({
            value: room.fullValue,
            label: room.fullLabel
          }))
          
          // 添加unitRoomResults到results，去重
          unitRoomResults.forEach(roomResult => {
            if (!results.some(result => result.value === roomResult.value)) {
              results.push(roomResult)
            }
          })
        }
      }
      
      // 去重并更新搜索结果
      this.searchResults = results
      this.isSearching = this.searchResults.length > 0
      
      // 当搜索结果只有一个时，自动选择该结果
      if (this.searchResults.length === 1) {
        this.$nextTick(() => {
          this.selectSearchResult(this.searchResults[0])
        })
      }
    },
    
    // 选择搜索结果
    selectSearchResult(result) {
      // 根据result.value的格式判断是楼栋、单元还是户号
      const valueParts = result.value.split('-')
      
      if (valueParts.length === 1) {
        // 楼栋
        this.selectedBuilding = result.value
        this.selectedUnit = ''
        this.selectedRoom = ''
        this.pureRoomNumber = ''
        this.displayValue = `${this.selectedBuilding}栋`
      } else if (valueParts.length === 2) {
        // 单元
        this.selectedBuilding = valueParts[0]
        this.selectedUnit = valueParts[1]
        this.selectedRoom = ''
        this.pureRoomNumber = ''
        this.displayValue = `${this.selectedBuilding}栋${this.selectedUnit}单元`
      } else {
        // 户号
        // 使用完整的value作为roomValue，参考building_data.js中的格式
        this.selectedRoom = result.value
        // 同时提取building、unit和纯房号信息
        if (valueParts.length >= 3) {
          this.selectedBuilding = valueParts[0]
          this.selectedUnit = valueParts[1]
          this.pureRoomNumber = valueParts[2] // 提取纯房号
        }
        this.displayValue = `${this.selectedBuilding}栋${this.selectedUnit}单元${this.pureRoomNumber}号`
      }
      
      // 关闭菜单
      this.hideMenu()
      
      // 重置搜索状态
      this.isSearching = false
      this.searchResults = []
    },
    
    // 清空选择
    clearSelection() {
      this.displayValue = ''
      this.selectedBuilding = ''
      this.selectedUnit = ''
      this.selectedRoom = ''
      
      // 关闭菜单
      this.hideMenu()
    },
    
    // 点击外部关闭菜单
    handleClickOutside(event) {
      if (this.isMenuVisible && !this.$el.contains(event.target)) {
        this.hideMenu()
      }
    }
  }
}
</script>

<style scoped>
.cascading-selector-container {
  position: relative;
  width: 100%;
  box-sizing: border-box;
}

.cascading-selector {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  align-items: center;
}

.cascading-selector-input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  line-height: 32px;
  color: #606266;
  background-color: #fff;
  box-sizing: border-box;
  transition: border-color 0.2s, box-shadow 0.2s;
  outline: none;
  padding-right: 30px;
  vertical-align: middle;
  font-family: Helvetica Neue, Helvetica, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Arial, sans-serif;
}

.cascading-selector-input:focus {
  border-color: #409eff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.cascading-clear-btn {
  cursor: pointer;
  z-index: 10;
  position: absolute;
  right: 5px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #999;
  font-size: 16px;
}

.cascading-menu {
  position: fixed;
  z-index: 9999;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  width: 100%;
}

.cascading-menu-item {
  padding: 8px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
  position: relative;
}

.cascading-menu-item:hover {
  background-color: #f0f0f0;
}

.cascading-menu-item.has-children::after {
  content: '▶';
  float: right;
  font-size: 10px;
  transition: transform 0.2s;
}

.cascading-menu-item.has-children:hover::after {
  transform: rotate(90deg);
}

.cascading-submenu {
  transition: display 0.2s;
}

.cascading-search-header {
  padding: 8px 12px;
  font-weight: bold;
  border-bottom: 1px solid #eee;
}

.cascading-search-results {
  padding: 0;
}

.cascading-menu-content {
  padding: 0;
}
</style>