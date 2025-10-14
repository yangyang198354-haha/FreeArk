# 导入Excel COM对象
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

# 打开Excel文件
$workbook = $excel.Workbooks.Open("c:\Users\yanggyan\TRAE\FreeArk\resource\大屏IP及MAC-20251005.xlsx")
$worksheet = $workbook.Worksheets.Item(1)

# 获取当前使用的行数
$usedRange = $worksheet.UsedRange
$lastRow = $usedRange.Rows.Count

# 插入新行作为表头
$worksheet.Rows(1).Insert()

# 设置表头
$worksheet.Cells(1, 1).Value2 = "楼栋"
$worksheet.Cells(1, 2).Value2 = "三恒系统控制柜主机IP地址"
$worksheet.Cells(1, 3).Value2 = "唯一标识符(MAC)"

# 设置表头样式（加粗）
$worksheet.Range("A1:C1").Font.Bold = $true

# 保存文件
$workbook.Save()

# 清理资源
$workbook.Close()
$excel.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($worksheet) | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()

Write-Host "Excel文件表头添加完成！"