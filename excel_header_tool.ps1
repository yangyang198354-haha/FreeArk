# 创建一个宏文件，用户可以在Excel中手动运行
$vbaCode = @"
Sub AddHeaderToExcel()
    ' 添加表头
    Rows(1).Insert Shift:=xlDown, CopyOrigin:=xlFormatFromLeftOrAbove
    Range("A1").Value = "楼栋"
    Range("B1").Value = "三恒系统控制柜主机IP地址"
    Range("C1").Value = "唯一标识符(MAC)"
    
    ' 设置表头样式
    Range("A1:C1").Font.Bold = True
    Range("A1:C1").HorizontalAlignment = xlCenter
    
    ' 自动调整列宽
    Columns("A:C").AutoFit
    
    ' 保存文件
    ActiveWorkbook.Save
    
    MsgBox "表头添加完成！"
End Sub
"@

# 将VBA代码保存到文本文件
$vbaCode | Out-File -FilePath "c:\Users\yanggyan\TRAE\FreeArk\ExcelHeaderMacro.txt" -Encoding utf8

Write-Host "已创建Excel宏代码文件：c:\Users\yanggyan\TRAE\FreeArk\ExcelHeaderMacro.txt"
Write-Host "请按照以下步骤操作："
Write-Host "1. 打开Excel文件 '大屏IP及MAC-20251005.xlsx'"
Write-Host "2. 按 Alt+F11 打开VBA编辑器"
Write-Host "3. 插入一个新模块（插入 > 模块）"
Write-Host "4. 将文本文件中的代码复制粘贴到模块中"
Write-Host "5. 按 F5 运行宏"
Write-Host "6. 关闭VBA编辑器，保存Excel文件"