import os
os.environ['TK_SILENCE_DEPRECATION'] = '1'

import re
import subprocess
from datetime import datetime
from tkinter import Tk
from tkinter.filedialog import askdirectory

import argparse

# 定義文件命名格式的正則表達式，允許 jpg 和 mp4 等副檔名
pattern1 = re.compile(r"^(.+?)_(\d+)_\d+_\d+\.(jpg|mp4)$")  # IG格式
pattern2 = re.compile(r"^(.+)-(\d{8})(\d{6})-\d+-\d+\.(jpg|mp4)$")  # Twitter格式

def main():
    parser = argparse.ArgumentParser(description="依據 Twitter/IG 檔名時間戳更新檔案建立時間與分類")
    parser.add_argument('-m', '-mv', '--move', dest='move', choices=['y', 'n', 'Y', 'N'], default=None, help='是否將檔案移動到子資料夾？(y/n)')
    parser.add_argument('-d', '-dir', '--dir', '--folder', dest='folder', default=None, help='要處理的資料夾路徑 (留空則彈窗選擇)')
    args = parser.parse_args()

    move_files = args.move.lower() if args.move else None
    if move_files is None:
        # 詢問是否要移動檔案
        while True:
            ans = input("是否要將檔案移動到子資料夾？(y/n): ").strip().lower()
            if ans in ['y', 'n']:
                move_files = ans
                break
            print("請輸入 y 或 n")

    folder_path = args.folder
    if not folder_path:
        # 隱藏主窗口
        root = Tk()
        root.withdraw()
        # 彈出資料夾選擇對話框
        folder_path = askdirectory(title='請選擇要處理的資料夾')
    
    if not folder_path or not os.path.exists(folder_path):
        print("未選擇有效資料夾，程序結束。")
        return
    
    print(f"正在處理資料夾：{folder_path}")

    
    # 遍歷文件夾中的文件
    for filename in os.listdir(folder_path):
        match1 = pattern1.match(filename)
        match2 = pattern2.match(filename)
        
        if match1:  # IG格式
            name = match1.group(1)
            timestamp = int(match1.group(2))
            date_obj = datetime.fromtimestamp(timestamp)
            
        elif match2:  # Twitter格式
            name = match2.group(1)
            date_str = match2.group(2)
            time_str = match2.group(3)
            date_obj = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
        else:
            print(f"不符合命名格式，跳過文件：{filename}")
            continue

        try:
            # 完整文件路徑
            file_path = os.path.join(folder_path, filename)
            
            # 設定新的時間戳
            new_datetime = date_obj.strftime('%Y%m%d%H%M.%S')
            subprocess.run(['touch', '-t', new_datetime, file_path])
            timestamp = date_obj.timestamp()
            os.utime(file_path, (timestamp, timestamp))
            
            # 根據用戶輸入決定是否移動檔案
            if move_files == 'y':
                if match1:
                    # 只在需要移動時才創建 IG 資料夾
                    ig_folder = os.path.join(folder_path, 'IG')
                    os.makedirs(ig_folder, exist_ok=True)
                    new_path = os.path.join(ig_folder, filename)
                else:
                    # 只在需要移動時才創建 Twitter 資料夾
                    twitter_folder = os.path.join(folder_path, 'Twitter')
                    os.makedirs(twitter_folder, exist_ok=True)
                    new_path = os.path.join(twitter_folder, filename)
                
                os.rename(file_path, new_path)
                print(f"更新並移動 {filename} 的創建時間為: {date_obj}")
            else:
                print(f"更新 {filename} 的創建時間為: {date_obj}")

        except ValueError as e:
            print(f"處理文件時發生錯誤，跳過文件：{filename}，錯誤：{str(e)}")

if __name__ == "__main__":
    main()
