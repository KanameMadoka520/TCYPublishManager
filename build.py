import os
import sys
import shutil

# === 配置区 ===
ICON_FILE = "icon.ico"
MAIN_SCRIPT = "TCYPublishManager.py"
EXE_NAME = "TCYPublishManager-1.0.0"
# 需要打包进 EXE 的额外文件
# 格式：("源文件", "目标路径")，目标路径 "." 表示根目录
ADDED_DATA = [("index.html", ".")]


def main():
    print("=" * 50)
    print("  TCY Publish Manager 自动构建工具")
    print("=" * 50)
    print()

    # 1. 检查必要文件
    if not os.path.exists(MAIN_SCRIPT):
        print(f"错误: 找不到主脚本 {MAIN_SCRIPT}")
        return

    for src, _ in ADDED_DATA:
        if not os.path.exists(src):
            print(f"错误: 找不到需要打包的文件 {src}")
            return

    # 2. 组装 PyInstaller 命令
    path_sep = ";" if os.name == 'nt' else ":"

    add_data_str = ""
    for src, dst in ADDED_DATA:
        add_data_str += f'--add-data="{src}{path_sep}{dst}" '

    cmd = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        f'--name="{EXE_NAME}"',
        add_data_str.strip(),
        MAIN_SCRIPT
    ]

    if os.path.exists(ICON_FILE):
        cmd.insert(4, f"--icon={ICON_FILE}")
        print(f"  图标: {ICON_FILE}")
    else:
        print(f"  提示: 未找到 {ICON_FILE}，将使用默认图标")

    cmd_str = " ".join(cmd)
    print(f"  主脚本: {MAIN_SCRIPT}")
    print(f"  输出名称: {EXE_NAME}.exe")
    print(f"  附加数据: {', '.join(src for src, _ in ADDED_DATA)}")
    print()
    print(f"  执行命令: {cmd_str}")
    print()

    # 3. 执行打包
    exit_code = os.system(cmd_str)

    # 4. 清理临时文件
    print()
    print("  正在清理临时文件...")
    spec_file = f"{EXE_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)
    if os.path.exists("build"):
        shutil.rmtree("build")

    if exit_code == 0:
        print()
        print("  构建成功！")
        print(f"  请在 dist 文件夹中查看: {EXE_NAME}.exe")
    else:
        print()
        print("  构建失败，请检查上方错误信息。")


if __name__ == "__main__":
    main()
