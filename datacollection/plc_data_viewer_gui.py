import os
import sys
import json
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import time
import pandas as pd
from datetime import datetime
import platform

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入数据收集管理器
from datacollection.improved_data_collection_manager import ImprovedDataCollectionManager

class PLCDataViewerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("朗诗乐府自由方舟累计用量采集程序")
        self.root.geometry("1000x600")
        self.root.minsize(800, 500)
        
        # 配置Windows风格
        self.configure_windows_style()
        
        # 设置中文字体支持
        self.setup_fonts()
        
        # 初始化变量
        self.selected_files = []
        self.data_collection_manager = None
        self.is_processing = False
        
        # 创建UI
        self.create_widgets()
        
        # 初始化数据收集管理器
        self.initialize_manager()
    
    def configure_windows_style(self):
        # 使用Windows系统主题
        if platform.system() == 'Windows':
            try:
                # 尝试使用ttk的Windows主题
                self.style = ttk.Style()
                # Windows下常见的主题有'clam', 'alt', 'default', 'classic'
                # 'clam'主题在不同系统上表现比较一致，且支持更多自定义
                self.style.theme_use('clam')
                
                # 配置按钮样式
                self.style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=6)
                
                # 配置标签样式
                self.style.configure('TLabel', font=('Microsoft YaHei UI', 10))
                
                # 配置表格样式
                self.style.configure('Treeview', 
                                     font=('Microsoft YaHei UI', 9),
                                     rowheight=22)
                self.style.configure('Treeview.Heading', 
                                     font=('Microsoft YaHei UI', 10, 'bold'),
                                     background='#E0E0E0')
                # 设置选中行的颜色
                self.style.map('Treeview', 
                               background=[('selected', '#0078D7')],
                               foreground=[('selected', 'white')])
            except:
                # 如果主题设置失败，使用默认配置
                pass
        else:
            # 非Windows系统使用默认主题
            self.style = ttk.Style()
    
    def setup_fonts(self):
        # 设置支持中文的字体
        if platform.system() == 'Windows':
            self.default_font = ('Microsoft YaHei UI', 10)
            self.header_font = ('Microsoft YaHei UI', 11, 'bold')
        else:
            self.default_font = ('SimHei', 10)
            self.header_font = ('SimHei', 11, 'bold')
    
    def initialize_manager(self):
        try:
            # 初始化数据收集管理器
            self.data_collection_manager = ImprovedDataCollectionManager(max_workers=5)
            self.data_collection_manager.start()
        except Exception as e:
            messagebox.showerror("初始化错误", f"无法初始化数据收集管理器: {str(e)}")
    
    def create_widgets(self):
        # 创建主框架，使用Windows标准的内边距
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建顶部控制区域，使用分组框样式
        group_frame = ttk.LabelFrame(main_frame, text="操作区", padding="8")
        group_frame.pack(fill=tk.X, side=tk.TOP, pady=(0, 10))
        
        # 控制按钮区域，使用水平分隔布局
        buttons_frame = ttk.Frame(group_frame)
        buttons_frame.pack(side=tk.LEFT, fill=tk.X)
        
        # 选择文件按钮
        self.select_files_btn = ttk.Button(buttons_frame, text="选择JSON配置文件", command=self.select_files)
        self.select_files_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # 开始读取按钮
        self.start_btn = ttk.Button(buttons_frame, text="开始读取PLC数据", command=self.start_data_collection)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # 导出数据按钮
        self.export_btn = ttk.Button(buttons_frame, text="导出数据", command=self.export_data)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # 文件列表标签区域，占满剩余空间
        file_info_frame = ttk.Frame(group_frame)
        file_info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        ttk.Label(file_info_frame, text="已选择文件:", font=self.default_font).pack(side=tk.LEFT)
        
        # 文件列表标签
        self.file_list_label = ttk.Label(file_info_frame, text="无", font=self.default_font)
        self.file_list_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 创建状态条，使用Windows标准样式
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, 
                                   relief=tk.SUNKEN, anchor=tk.W, 
                                   padding=(5, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建数据展示区域，使用分组框样式
        data_frame = ttk.LabelFrame(main_frame, text="数据展示", padding="8")
        data_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建表格框架，包含滚动条
        table_frame = ttk.Frame(data_frame)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建垂直滚动条
        y_scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        y_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建水平滚动条
        x_scrollbar = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        x_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建表格，增加显示行数
        self.tree = ttk.Treeview(table_frame, 
                                yscrollcommand=y_scrollbar.set, 
                                xscrollcommand=x_scrollbar.set, 
                                selectmode='extended')
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        y_scrollbar.config(command=self.tree.yview)
        x_scrollbar.config(command=self.tree.xview)
        
        # 定义表格列
        columns = ("building", "room", "location", "hot_quantity", "cold_quantity", "status", "timestamp")
        self.tree["columns"] = columns
        
        # 设置列宽和标题
        self.tree.column("#0", width=0, stretch=tk.NO)  # 隐藏第一列
        self.tree.column("building", width=100, anchor=tk.CENTER)
        self.tree.column("room", width=100, anchor=tk.CENTER)
        self.tree.column("location", width=200, anchor=tk.W)
        self.tree.column("hot_quantity", width=120, anchor=tk.CENTER)
        self.tree.column("cold_quantity", width=120, anchor=tk.CENTER)
        self.tree.column("status", width=80, anchor=tk.CENTER)
        self.tree.column("timestamp", width=150, anchor=tk.CENTER)
        
        # 设置列标题
        self.tree.heading("building", text="楼栋")
        self.tree.heading("room", text="房间号")
        self.tree.heading("location", text="专有部分坐落")
        self.tree.heading("hot_quantity", text="累计制热量")
        self.tree.heading("cold_quantity", text="累计制冷量")
        self.tree.heading("status", text="状态")
        self.tree.heading("timestamp", text="采集时间")
        
        # 启用表格排序功能
        for col in columns:
            self.tree.heading(col, text=self.tree.heading(col)["text"], 
                             command=lambda _col=col: self.treeview_sort_column(_col, False))
    
    def select_files(self):
        # 打开文件选择对话框
        file_paths = filedialog.askopenfilenames(
            title="选择JSON配置文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            initialdir="c:/Users/yanggyan/TRAE/FreeArk/resource/"
        )
        
        if file_paths:
            self.selected_files = list(file_paths)
            # 更新文件列表显示
            file_count = len(self.selected_files)
            if file_count <= 3:
                file_names = ", ".join([os.path.basename(f) for f in self.selected_files])
            else:
                file_names = f"已选择 {file_count} 个文件: {os.path.basename(self.selected_files[0])} 等"
            self.file_list_label.config(text=file_names)
            self.status_var.set(f"已选择 {file_count} 个配置文件")
    
    def start_data_collection(self):
        if self.is_processing:
            messagebox.showinfo("提示", "正在处理数据，请稍候...")
            return
        
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择配置文件")
            return
        
        if not self.data_collection_manager:
            messagebox.showerror("错误", "数据收集管理器未初始化")
            return
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 禁用按钮
        self.select_files_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.is_processing = True
        self.status_var.set("正在处理数据，请稍候...")
        
        # 在新线程中处理数据
        threading.Thread(target=self.process_files, daemon=True).start()
    
    def process_files(self):
        try:
            total_files = len(self.selected_files)
            processed_files = 0
            
            for file_path in self.selected_files:
                processed_files += 1
                file_name = os.path.basename(file_path)
                self.status_var.set(f"正在处理文件 {processed_files}/{total_files}: {file_name}")
                
                # 调用数据收集管理器实时读取PLC数据
                self.status_var.set(f"正在从PLC读取数据: {file_name}")
                # 直接使用文件名调用collect_data_for_building方法
                plc_data = self.data_collection_manager.collect_data_for_building(file_name)
                
                if plc_data:
                    # 提取楼栋信息
                    building_name = file_name.split('_')[0] if '_' in file_name else "未知楼栋"
                    
                    # 处理从PLC读取的数据
                    self.process_file_content(plc_data, building_name)
                else:
                    self.status_var.set(f"无法从PLC读取数据: {file_name}")
            
            self.status_var.set(f"处理完成，共 {processed_files} 个文件，表格中显示 {len(self.tree.get_children())} 条记录")
        
        except Exception as e:
            self.status_var.set(f"处理出错: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理文件时出错: {str(e)}"))
        
        finally:
            # 恢复按钮状态
            self.root.after(0, lambda: self.select_files_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.is_processing = False
    
    def process_file_content(self, file_data, building_name):
        # 检查数据格式并处理
        if isinstance(file_data, dict):
            # 检查是否是合并后的all_onwer.json格式
            if 'buildings' in file_data:
                for building in file_data['buildings']:
                    building_content = building.get('content', {})
                    self._process_room_data(building_content, building_name)
            else:
                # 单个建筑的数据文件格式
                self._process_room_data(file_data, building_name)
        elif isinstance(file_data, list):
            # 列表格式数据
            for item in file_data:
                if isinstance(item, dict):
                    # 处理每个房间的数据
                    self._process_single_room_data(item, building_name)
    
    def _process_room_data(self, room_data, building_name):
        for room_id, room_info in room_data.items():
            self._process_single_room_data(room_info, building_name, room_id)
    
    def _process_single_room_data(self, room_info, building_name, room_id=None):
        # 提取房间信息
        location = room_info.get("专有部分坐落", "未知坐落")
        room_number = room_id or room_info.get("户号", "未知房间")
        
        # 提取热冷量数据
        data_section = room_info.get("data", {})
        hot_quantity = "-"
        cold_quantity = "-"
        status = "未知"
        timestamp = ""
        
        if isinstance(data_section, dict):
            # 处理累计制热量 - 支持不同的参数键名
            hot_keys = ["total_hot_quantity", "累计制热量", "累计热量"]
            for key in hot_keys:
                if key in data_section:
                    hot_data = data_section[key]
                    if isinstance(hot_data, dict) and hot_data.get("success", False):
                        hot_quantity = str(hot_data.get("value", "-"))
                    elif not isinstance(hot_data, dict):
                        hot_quantity = str(hot_data)
                    else:
                        hot_quantity = "失败"
                    break
            
            # 处理累计制冷量 - 支持不同的参数键名
            cold_keys = ["total_cold_quantity", "累计制冷量", "累计冷量"]
            for key in cold_keys:
                if key in data_section:
                    cold_data = data_section[key]
                    if isinstance(cold_data, dict) and cold_data.get("success", False):
                        cold_quantity = str(cold_data.get("value", "-"))
                    elif not isinstance(cold_data, dict):
                        cold_quantity = str(cold_data)
                    else:
                        cold_quantity = "失败"
                    break
        
        # 提取状态和时间戳
        status = room_info.get("status", "未知")
        timestamp = room_info.get("timestamp", "")
        
        # 在GUI线程中添加数据到表格
        self.root.after(0, self.add_item_to_tree, building_name, room_number, location, hot_quantity, cold_quantity, status, timestamp)
    
    def add_item_to_tree(self, building, room, location, hot, cold, status, timestamp):
        # 插入数据到表格
        self.tree.insert("", tk.END, values=(building, room, location, hot, cold, status, timestamp))
    
    def treeview_sort_column(self, col, reverse):
        """表格排序功能"""
        # 获取所有数据
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # 尝试按数字排序，如果失败则按字符串排序
        try:
            l.sort(key=lambda t: float(t[0]) if t[0] not in ['-', '未知'] else 0, reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)
        
        # 重新排列数据
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        
        # 切换排序方向
        self.tree.heading(col, command=lambda: self.treeview_sort_column(col, not reverse))
    
    def export_data(self):
        # 获取表格中的所有数据
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("提示", "表格中没有数据可导出")
            return
        
        # 显示导出格式选择对话框，使用Windows风格的对话框
        export_window = tk.Toplevel(self.root)
        export_window.title("导出数据")
        export_window.resizable(False, False)  # 禁止调整大小
        
        # 设置窗口样式
        if hasattr(self, 'style'):
            # 使用ttk的框架以保持一致性
            content_frame = ttk.Frame(export_window, padding="10")
            content_frame.pack(fill=tk.BOTH, expand=True)
        else:
            content_frame = export_window
        
        # 模态对话框设置
        export_window.transient(self.root)
        export_window.grab_set()
        
        # 计算并设置对话框在主窗口中央显示
        export_window.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()
        
        dialog_width = 300
        dialog_height = 160
        
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        
        export_window.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # 添加标题，调整字体大小
        ttk.Label(content_frame, text="请选择导出格式:", font=(self.default_font[0], self.default_font[1], 'bold')).pack(pady=8)
        
        # 创建格式选择框架，调整间距
        format_frame = ttk.Frame(content_frame)
        format_frame.pack(pady=5)
        
        format_var = tk.StringVar(value="json")
        
        # 添加单选按钮，增加内边距
        ttk.Radiobutton(format_frame, text="JSON格式", variable=format_var, value="json").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(format_frame, text="Excel格式", variable=format_var, value="xlsx").pack(anchor=tk.W, pady=2)
        
        def do_export():
            export_format = format_var.get()
            export_window.destroy()
            
            # 根据选择的格式导出数据
            if export_format == "json":
                self._export_to_json()
            else:
                self._export_to_excel()
        
        # 创建按钮框架，使用Windows标准的按钮布局（确认在右）
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(pady=10, anchor=tk.E)
        
        # 取消按钮在左，确认按钮在右，符合Windows规范
        ttk.Button(btn_frame, text="取消", command=export_window.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="确认", command=do_export).pack(side=tk.LEFT, padx=5)
    
    def _export_to_json(self):
        try:
            # 获取表格数据
            data = []
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                data.append({
                    "楼栋": values[0],
                    "房间号": values[1],
                    "专有部分坐落": values[2],
                    "累计制热量": values[3],
                    "累计制冷量": values[4],
                    "状态": values[5],
                    "采集时间": values[6]
                })
            
            # 打开文件保存对话框
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"plc_data_export_{timestamp}.json"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
            
            if file_path:
                # 保存数据到JSON文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.status_var.set(f"数据已成功导出到: {file_path}")
                messagebox.showinfo("成功", f"数据已成功导出到:\n{file_path}")
        
        except Exception as e:
            self.status_var.set(f"导出JSON文件时出错: {str(e)}")
            messagebox.showerror("错误", f"导出JSON文件时出错:\n{str(e)}")
    
    def _export_to_excel(self):
        try:
            # 获取表格数据
            data = []
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                data.append({
                    "楼栋": values[0],
                    "房间号": values[1],
                    "专有部分坐落": values[2],
                    "累计制热量": values[3],
                    "累计制冷量": values[4],
                    "状态": values[5],
                    "采集时间": values[6]
                })
            
            # 创建DataFrame
            df = pd.DataFrame(data)
            
            # 打开文件保存对话框
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"plc_data_export_{timestamp}.xlsx"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
            
            if file_path:
                # 保存数据到Excel文件
                with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='PLC数据')
                    
                    # 获取xlsxwriter工作簿和工作表对象
                    workbook = writer.book
                    worksheet = writer.sheets['PLC数据']
                    
                    # 设置列宽
                    worksheet.set_column('A:A', 10)  # 楼栋
                    worksheet.set_column('B:B', 10)  # 房间号
                    worksheet.set_column('C:C', 25)  # 专有部分坐落
                    worksheet.set_column('D:G', 15)  # 其他列
                    
                    # 添加表头样式
                    header_format = workbook.add_format({
                        'bold': True,
                        'text_wrap': True,
                        'valign': 'top',
                        'fg_color': '#D7E4BC',
                        'border': 1})
                    
                    # 应用表头样式
                    for col_num, value in enumerate(df.columns.values):
                        worksheet.write(0, col_num, value, header_format)
            
            self.status_var.set(f"数据已成功导出到: {file_path}")
            messagebox.showinfo("成功", f"数据已成功导出到:\n{file_path}")
        
        except Exception as e:
            self.status_var.set(f"导出Excel文件时出错: {str(e)}")
            messagebox.showerror("错误", f"导出Excel文件时出错:\n{str(e)}")
    
    def on_closing(self):
        # 清理资源
        if self.data_collection_manager:
            self.data_collection_manager.stop()
        self.root.destroy()

if __name__ == "__main__":
    # 创建主窗口
    root = tk.Tk()
    
    # 设置应用程序图标（如果有）
    # 可以添加Windows风格的图标
    
    # 创建应用实例
    app = PLCDataViewerGUI(root)
    
    # 设置关闭回调
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # 运行主循环
    root.mainloop()