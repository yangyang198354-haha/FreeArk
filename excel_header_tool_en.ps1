# Create a macro file that users can run manually in Excel
$vbaCode = @"
Sub AddHeaderToExcel()
    ' Add header row
    Rows(1).Insert Shift:=xlDown, CopyOrigin:=xlFormatFromLeftOrAbove
    Range("A1").Value = "Building"
    Range("B1").Value = "IP Address"
    Range("C1").Value = "MAC Address"
    
    ' Set header style
    Range("A1:C1").Font.Bold = True
    Range("A1:C1").HorizontalAlignment = xlCenter
    
    ' Auto-fit columns
    Columns("A:C").AutoFit
    
    ' Save file
    ActiveWorkbook.Save
    
    MsgBox "Header added successfully!"
End Sub
"@

# Save VBA code to text file
$vbaCode | Out-File -FilePath "c:\Users\yanggyan\TRAE\FreeArk\ExcelHeaderMacro.txt" -Encoding utf8

Write-Host "Excel macro code file created: c:\Users\yanggyan\TRAE\FreeArk\ExcelHeaderMacro.txt"
Write-Host "Please follow these steps:" -ForegroundColor Green
Write-Host "1. Open the Excel file '大屏IP及MAC-20251005.xlsx'"
Write-Host "2. Press Alt+F11 to open VBA Editor"
Write-Host "3. Insert a new module (Insert > Module)"
Write-Host "4. Copy and paste the code from the text file into the module"
Write-Host "5. Press F5 to run the macro"
Write-Host "6. Close VBA Editor and save the Excel file"