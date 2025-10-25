const fs = require('fs');
const path = require('path');

// 读取源数据文件
const sourceFilePath = 'c:/Users/yanggyan/TRAE/FreeArk/resource/all_onwer.json';
const targetFilePath = 'c:/Users/yanggyan/TRAE/FreeArk/FreeArkWeb/frontend/building_data.js';

try {
    // 读取源数据
    const sourceData = JSON.parse(fs.readFileSync(sourceFilePath, 'utf8'));
    
    // 数据结构：楼栋 -> 单元 -> 户号
    const buildingMap = new Map();
    
    // 遍历所有数据
    Object.values(sourceData).forEach(item => {
        // 提取楼栋号（去除'栋'字）
        const buildingNum = item['楼栋'].replace('栋', '');
        // 提取单元号（去除'单元'字）
        const unitNum = item['单元'].replace('单元', '');
        // 户号
        const roomNum = String(item['户号']);
        
        // 初始化楼栋
        if (!buildingMap.has(buildingNum)) {
            buildingMap.set(buildingNum, {
                value: buildingNum,
                label: `${buildingNum}栋`,
                children: []
            });
        }
        
        const building = buildingMap.get(buildingNum);
        
        // 查找或初始化单元
        let unit = building.children.find(u => u.value === unitNum);
        if (!unit) {
            unit = {
                value: unitNum,
                label: `${unitNum}单元`,
                children: []
            };
            building.children.push(unit);
        }
        
        // 添加户号（避免重复）
        if (!unit.children.find(r => r.value === roomNum)) {
            unit.children.push({
                value: roomNum,
                label: `${roomNum}室`
            });
        }
    });
    
    // 排序：楼栋按数字排序
    const sortedBuildings = Array.from(buildingMap.values()).sort((a, b) => 
        parseInt(a.value) - parseInt(b.value)
    );
    
    // 对每个楼栋的单元进行排序
    sortedBuildings.forEach(building => {
        building.children.sort((a, b) => 
            parseInt(a.value) - parseInt(b.value)
        );
        
        // 对每个单元的户号进行排序
        building.children.forEach(unit => {
            unit.children.sort((a, b) => 
                parseInt(a.value) - parseInt(b.value)
            );
        });
    });
    
    // 生成JavaScript文件内容
    const fileContent = `// 楼栋-单元-房号级联菜单数据
const buildingData = ${JSON.stringify(sortedBuildings, null, 2)};`;
    
    // 写入目标文件
    fs.writeFileSync(targetFilePath, fileContent, 'utf8');
    
    console.log('Building data generated successfully!');
    console.log(`Total buildings: ${sortedBuildings.length}`);
    
    // 统计总数据量
    let totalRooms = 0;
    sortedBuildings.forEach(building => {
        building.children.forEach(unit => {
            totalRooms += unit.children.length;
        });
    });
    
    console.log(`Total rooms: ${totalRooms}`);
    
} catch (error) {
    console.error('Error generating building data:', error.message);
}