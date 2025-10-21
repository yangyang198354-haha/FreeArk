from PIL import Image
import os

# 输入和输出文件路径
input_jpg = r'c:/Users/yanggyan/TRAE/FreeArk/resource/GUI icon.jpg'
output_ico = r'c:/Users/yanggyan/TRAE/FreeArk/resource/GUI icon.ico'

# 检查输入文件是否存在
if not os.path.exists(input_jpg):
    print(f"错误：找不到输入文件 {input_jpg}")
    exit(1)

try:
    # 打开JPG图片
    img = Image.open(input_jpg)
    
    # 转换并保存为ICO格式
    # 使用多种尺寸以确保兼容性
    img.save(output_ico, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128)])
    
    print(f"成功：已将 {input_jpg} 转换为 {output_ico}")
    print(f"ICO文件大小：{os.path.getsize(output_ico)} 字节")
    
except Exception as e:
    print(f"错误：转换失败 - {str(e)}")