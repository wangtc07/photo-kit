#!/usr/bin/env python3
import os
import sys
import subprocess

try:
    import readline
    import atexit
    histfile = os.path.join(os.path.expanduser("~"), ".photo_kit_history")
    try:
        readline.read_history_file(histfile)
        readline.set_history_length(100)
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, histfile)
except ImportError:
    pass

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    options = {
        '1': ('照片加白邊與浮水印 (wbg.py)', 'src/watermark/wbg.py'),
        '2': ('批次壓縮圖片 (compress_images.py)', 'src/image_process/compress_images.py'),
        '3': ('合併多張照片 (自動白邊排版) (combine_photos.py)', 'src/image_process/combine_photos.py'),
        '4': ('圖片轉影片 (支援迴圈) (img2video.py)', 'src/video_gen/img2video.py'),
        '5': ('檔案整理工具 (move.py)', 'src/file_manage/move.py'),
        '6': ('依格式重命名工具 (reCreateTime.py)', 'src/file_manage/reCreateTime.py'),
        '7': ('連拍廢片清理 (burst_filter.py)', 'src/file_manage/burst_filter.py'),
        '8': ('匯出 Capture One 資料夾清單 (export_c1_folders.py)', 'src/file_manage/export_c1_folders.py'),
        '9': ('チェキ自動裁切 (cheki_crop.py)', 'src/image_process/cheki_crop.py'),
        '10': ('去除白邊 (remove_white_borders.py)', 'src/image_process/remove_white_borders.py'),
        'q': ('退出', None)
    }

    while True:
        clear_screen()
        print("="*50)
        print(" photo-kit 工具整合啟動器")
        print("="*50)
        for key, (desc, _) in options.items():
            print(f"[{key}] {desc}")
        print("="*50)
        
        choice = input("請選擇要執行的機能 (例如: 1): ").strip().lower()
        if not choice:
            continue
            
        if choice == 'q':
            print("退出程式。")
            break
        
        if choice in options:
            script_path = os.path.join(base_dir, options[choice][1])
            
            # 清空畫面，顯示選擇的機能
            clear_screen()
            print("="*50)
            print(f" 已選擇: {options[choice][0]}")
            print("="*50)
            
            # 顯示該腳本的參數說明
            try:
                env = os.environ.copy()
                print("\n[可用參數說明]")
                subprocess.run([sys.executable, script_path, "--help"], env=env)
                print("-" * 50)
            except Exception as e:
                print(f"無法獲取參數說明: {e}")

            # 要求輸入參數
            args_input = input("\n請輸入附加參數 (若無請直接按 Enter): ").strip()
            
            import shlex
            try:
                args = shlex.split(args_input) if args_input else []
            except ValueError as e:
                print(f"參數解析錯誤: {e}")
                input("\n按 Enter 鍵返回主選單...")
                continue

            args_str = " ".join(args) if args else "(無)"
            print(f"\n準備執行: {options[choice][0]}")
            print(f"帶入參數: {args_str}\n")
            
            try:
                cmd = [sys.executable, script_path] + args
                subprocess.run(cmd, env=env)
            except KeyboardInterrupt:
                print("\n[使用者中斷]")
            except Exception as e:
                print(f"執行發生錯誤: {e}")
            
            input("\n按 Enter 鍵返回主選單...")
        else:
            input("\n無效的選項，按 Enter 鍵重試...")

if __name__ == "__main__":
    main()
