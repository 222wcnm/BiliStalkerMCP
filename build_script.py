#!/usr/bin/env python3
"""
BiliStalkerMCP 构建脚本

用于构建和发布包到 PyPI
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(cmd, cwd=None):
    """运行命令并返回结果"""
    print(f"运行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"命令执行失败: {result.stderr}")
        return False
    print(result.stdout)
    return True


def clean_build():
    """清理构建目录"""
    print("清理构建目录...")
    for dir_name in ["build", "dist", "*.egg-info"]:
        for path in Path(".").glob(dir_name):
            if path.is_dir():
                print(f"删除目录: {path}")
                shutil.rmtree(path)
            else:
                print(f"删除文件: {path}")
                path.unlink()


def install_build_tools():
    """安装构建工具"""
    print("安装构建工具...")
    commands = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "build", "twine", "wheel", "setuptools"]
    ]
    
    for cmd in commands:
        if not run_command(cmd):
            print(f"安装构建工具失败: {' '.join(cmd)}")
            return False
    return True


def build_package():
    """构建包"""
    print("构建包...")
    # 直接调用 build 模块而不是通过脚本
    if not run_command([sys.executable, "-m", "build"]):
        print("构建包失败")
        return False
    return True


def check_package():
    """检查构建的包"""
    print("检查构建的包...")
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print("dist 目录不存在")
        return False
    
    files = list(dist_dir.glob("*"))
    if not files:
        print("dist 目录为空")
        return False
    
    print("构建的文件:")
    for file in files:
        print(f"  - {file.name}")
    
    # 检查包内容
    for file in files:
        if file.suffix in [".whl", ".tar.gz"]:
            print(f"\n检查 {file.name} 内容:")
            if file.suffix == ".whl":
                run_command(["python", "-m", "wheel", "unpack", "--dest", "/tmp", str(file)])
            else:
                run_command(["tar", "-tzf", str(file)])
    
    return True


def upload_to_test_pypi():
    """上传到测试 PyPI"""
    print("上传到测试 PyPI...")
    cmd = [sys.executable, "-m", "twine", "upload", "--repository", "testpypi", "dist/*"]
    if not run_command(cmd):
        print("上传到测试 PyPI 失败")
        return False
    return True


def upload_to_pypi():
    """上传到 PyPI"""
    print("上传到 PyPI...")
    cmd = [sys.executable, "-m", "twine", "upload", "dist/*"]
    if not run_command(cmd):
        print("上传到 PyPI 失败")
        return False
    return True


def main():
    """主函数"""
    print("BiliStalkerMCP 构建脚本")
    print("=" * 50)
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python build.py clean          # 清理构建目录")
        print("  python build.py install       # 安装构建工具")
        print("  python build.py build         # 构建包")
        print("  python build.py check         # 检查构建的包")
        print("  python build.py test-upload   # 上传到测试 PyPI")
        print("  python build.py upload        # 上传到 PyPI")
        print("  python build.py all           # 执行完整流程（除了上传）")
        print("  python build.py release       # 执行完整流程并上传到 PyPI")
        return
    
    command = sys.argv[1]
    
    if command == "clean":
        clean_build()
    elif command == "install":
        install_build_tools()
    elif command == "build":
        if install_build_tools():
            clean_build()
            build_package()
            check_package()
    elif command == "check":
        check_package()
    elif command == "test-upload":
        upload_to_test_pypi()
    elif command == "upload":
        upload_to_pypi()
    elif command == "all":
        if install_build_tools():
            clean_build()
            if build_package():
                check_package()
    elif command == "release":
        if install_build_tools():
            clean_build()
            if build_package():
                if check_package():
                    if input("确定要上传到 PyPI 吗？(y/N): ").lower() == 'y':
                        upload_to_pypi()
                    else:
                        print("取消上传")
    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()