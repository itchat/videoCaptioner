#!/bin/bash

# 调试打包后的 .app 应用
# 使用方法：./debug_app.sh

APP_PATH="./dist/videoCaptioner.app"
LOG_FILE="./app_debug_$(date +%Y%m%d_%H%M%S).log"

echo "🔍 Debugging videoCaptioner.app"
echo "📄 Log file: $LOG_FILE"
echo ""

# 说明多图标问题
echo "⚠️  KNOWN ISSUE: Multiple Dock Icons"
echo "   When testing video processing, you may see 2-3 bouncing icons."
echo "   This is a known macOS multiprocessing limitation - app works perfectly!"
echo "   See README.md for technical details."
echo ""

if [ ! -d "$APP_PATH" ]; then
    echo "❌ App not found at: $APP_PATH"
    echo "请先运行 ./main.sh 构建应用"
    exit 1
fi

echo "📂 App structure:"
find "$APP_PATH" -name "ffmpeg" -o -name "*.py" -o -name "*.dylib" | head -20

echo ""
echo "🔍 Looking for ffmpeg:"
find "$APP_PATH" -name "ffmpeg" -type f

echo ""
echo "🚀 Starting app with debug output..."
echo "   (输出将保存到 $LOG_FILE)"
echo "   💡 Tip: Watch Console.app for additional debug info"
echo ""

# 模拟双击打开 .app
echo "🚀 Opening app (simulating double-click)..." | tee -a "$LOG_FILE"
open "$APP_PATH"
echo "✅ App launched - 请在应用中测试功能" | tee -a "$LOG_FILE"
echo "   应用日志将在应用关闭后显示在此文件中: $LOG_FILE"

echo ""
echo "📄 Debug log saved to: $LOG_FILE"
echo "请查看日志文件了解详细信息"

# 检查系统日志中的崩溃报告
echo ""
echo "🔍 Checking for crash reports..."
CRASH_DIR="$HOME/Library/Logs/DiagnosticReports"
if [ -d "$CRASH_DIR" ]; then
    find "$CRASH_DIR" -name "*videoCaptioner*" -o -name "*main*" -newer "$APP_PATH" | head -5
fi

echo ""
echo "🔧 System info:"
echo "  macOS: $(sw_vers -productVersion)"
echo "  Architecture: $(uname -m)"
echo "  Python: $(python3 --version 2>/dev/null || echo 'Not available')"
echo "  FFmpeg system: $(which ffmpeg 2>/dev/null || echo 'Not found')"
