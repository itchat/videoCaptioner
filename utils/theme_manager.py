"""
主题管理器
处理应用程序的主题设置和字体配置
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont


class ThemeManager:
    """主题管理器类"""
    
    def __init__(self):
        self.available_themes = []
        self.current_theme = "dark_teal.xml"
        self.font_database = None
        self._qt_material = None
    
    def _import_qt_material(self):
        """延迟导入 qt_material"""
        if self._qt_material is None:
            try:
                # 临时禁用警告
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    import qt_material
                self._qt_material = qt_material
                try:
                    self.available_themes = qt_material.list_themes()
                except Exception:
                    self.available_themes = ["dark_teal.xml", "light_blue.xml"]
            except ImportError:
                self._qt_material = False
                print("⚠️  qt_material 不可用，使用默认主题")
        return self._qt_material
    
    def setup_fonts(self, app: QApplication):
        """设置应用程序字体"""
        try:
            # 在 PyQt6 中，使用静态方法获取字体信息
            font_families = QFontDatabase.families()
            
            # macOS 推荐字体顺序
            preferred_fonts = [
                "San Francisco",  # macOS 系统字体
                ".SF NS Text",    # macOS 系统字体的内部名称
                "Helvetica Neue", # macOS 备选字体
                "Arial",          # 通用字体
                "Roboto",         # Material Design 字体
            ]
            
            selected_font = None
            for font_name in preferred_fonts:
                if font_name in font_families:
                    selected_font = font_name
                    break
            
            if selected_font:
                font = QFont(selected_font, 12)
                font.setStyleHint(QFont.StyleHint.SansSerif)
                app.setFont(font)
                print(f"✅ 设置字体: {selected_font}")
            else:
                # 使用系统默认字体
                print("ℹ️  使用系统默认字体")
                
        except Exception as e:
            print(f"⚠️  字体设置失败: {e}")
    
    def apply_theme(self, app: QApplication, theme_name: str = None):
        """应用主题"""
        qt_material = self._import_qt_material()
        
        if not qt_material:
            print("⚠️  qt_material 不可用，使用默认主题")
            return False
        
        try:
            theme = theme_name or self.current_theme
            
            # 确保主题名称有效
            if theme not in self.available_themes and self.available_themes:
                theme = "dark_teal.xml"
            
            # 应用主题
            qt_material.apply_stylesheet(app, theme=theme)
            self.current_theme = theme
            print(f"✅ 主题应用成功: {theme}")
            return True
            
        except Exception as e:
            print(f"⚠️  主题应用失败: {e}")
            return False
    
    def setup_macos_optimizations(self):
        """设置 macOS 特定的优化"""
        if sys.platform == "darwin":
            # 设置 macOS 特定的环境变量
            os.environ.setdefault('QT_MAC_WANTS_LAYER', '1')
            os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
            
            # 禁用一些可能引起问题的 Qt 功能
            os.environ.setdefault('QT_LOGGING_RULES', 'qt.svg.debug=false')
            
            print("✅ macOS 优化设置完成")
    
    def get_available_themes(self):
        """获取可用主题列表"""
        qt_material = self._import_qt_material()
        return self.available_themes.copy() if qt_material else []
    
    def is_theme_available(self):
        """检查主题功能是否可用"""
        qt_material = self._import_qt_material()
        return bool(qt_material)


# 全局主题管理器实例
theme_manager = ThemeManager()
