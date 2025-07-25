# PyQt6 升级指南

## 升级概述

本项目已成功从 PyQt5 升级到 PyQt6。以下是主要的变更内容和注意事项。

## 主要变更

### 1. 依赖更新
- `requirements.txt`: PyQt5 → PyQt6
- 保持其他依赖不变

### 2. 导入语句更新
```python
# 旧的 PyQt5 导入
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

# 新的 PyQt6 导入
from PyQt6.QtWidgets import QApplication, QMainWindow  
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
```

### 3. 枚举常量变更

PyQt6 将许多常量移动到了枚举类中：

#### Qt 常量
```python
# PyQt5
Qt.Window → Qt.WindowType.Window
Qt.AlignCenter → Qt.AlignmentFlag.AlignCenter
Qt.ScrollBarAlwaysOff → Qt.ScrollBarPolicy.ScrollBarAlwaysOff
Qt.WindowStaysOnTopHint → Qt.WindowType.WindowStaysOnTopHint

# QMessageBox 标准按钮
QMessageBox.Ok → QMessageBox.StandardButton.Ok
QMessageBox.Yes → QMessageBox.StandardButton.Yes
QMessageBox.No → QMessageBox.StandardButton.No

# QLineEdit 回显模式
QLineEdit.Password → QLineEdit.EchoMode.Password
```

### 4. 方法名变更
```python
# PyQt5
app.exec_() → app.exec()
dialog.exec_() → dialog.exec()
```

### 5. QAction 导入位置变更
```python
# PyQt5
from PyQt5.QtWidgets import QAction

# PyQt6  
from PyQt6.QtGui import QAction
```

## 更新的文件列表

1. **src/main.py** - 主入口文件导入更新
2. **utils/theme_manager.py** - 主题管理器导入更新
3. **utils/log_filter.py** - 日志过滤器导入更新
4. **core/worker_signals.py** - 工作信号导入更新
5. **core/video_processor.py** - 视频处理器导入更新
6. **src/ui/main_window.py** - 主窗口导入和常量更新
7. **src/ui/drop_area.py** - 拖放区域导入更新
8. **src/ui/progress_widget.py** - 进度组件导入更新
9. **src/ui/api_settings_dialog.py** - API设置对话框导入和常量更新
10. **src/ui/download_dialog.py** - 下载对话框导入更新
11. **requirements.txt** - 依赖更新

## 安装和测试

### 自动安装
```bash
./install_pyqt6.sh
```

### 手动安装
```bash
# 卸载 PyQt5
pip uninstall PyQt5 -y

# 安装 PyQt6
pip install PyQt6

# 安装其他依赖
pip install -r requirements.txt
```

### 测试升级
```bash
# 运行兼容性测试
python test_pyqt6.py

# 启动应用程序
python src/main.py
```

## 兼容性注意事项

1. **Qt Material 主题**: 需要确保使用的 qt-material 版本支持 PyQt6
2. **第三方库**: 某些使用 PyQt5 的第三方库可能需要更新
3. **信号连接**: PyQt6 中信号连接的类型检查更严格
4. **枚举类型**: 所有 Qt 常量现在都是强类型枚举

## 潜在问题和解决方案

### 问题1: qt-material 兼容性
如果 qt-material 不支持 PyQt6，可以：
- 使用 PyQt6 原生样式
- 寻找支持 PyQt6 的替代主题库
- 自定义 CSS 样式

### 问题2: 类型错误
PyQt6 的类型检查更严格，可能需要：
- 明确指定枚举类型
- 检查信号连接的参数类型

### 问题3: 缺少导入
某些组件的导入位置发生变化：
- QAction 从 QtWidgets 移动到 QtGui
- 某些枚举值需要完整路径

## 性能和功能改进

PyQt6 相比 PyQt5 的改进：
- 更好的内存管理
- 改进的信号系统
- 更强的类型安全
- 更现代的 API 设计
- 更好的 macOS 支持

## 回滚方案

如果需要回滚到 PyQt5：
1. 恢复所有文件的 PyQt5 导入
2. 恢复旧的常量格式
3. 更新 requirements.txt
4. 重新安装 PyQt5 依赖

保留此文档作为升级记录，以便将来参考和维护。
