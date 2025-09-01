@echo off
REM BiliStalkerMCP Windows 构建脚本

echo BiliStalkerMCP 构建脚本
echo ========================

if "%1"=="" (
    echo 用法:
    echo   build.bat clean          # 清理构建目录
    echo   build.bat install       # 安装构建工具
    echo   build.bat build         # 构建包
    echo   build.bat check         # 检查构建的包
    echo   build.bat test-upload   # 上传到测试 PyPI
    echo   build.bat upload        # 上传到 PyPI
    echo   build.bat all           # 执行完整流程（除了上传）
    echo   build.bat release       # 执行完整流程并上传到 PyPI
    exit /b 0
)

python build.py %1