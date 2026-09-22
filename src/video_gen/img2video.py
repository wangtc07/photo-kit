import glob
import os
import argparse



def main(name, fps, pattern='*.jpg', loop=False):
    import cv2
    import numpy as np
    img_array = []

    downloads_dir = os.path.expanduser('~/Downloads')
    directory_path = os.path.join(downloads_dir, name)
    file_pattern = pattern

    # 獲取檔案名稱列表
    file_list = glob.glob(os.path.join(directory_path, file_pattern))

    # 根據檔名（basename）對檔案名稱進行排序
    sorted_file_list = sorted(file_list, key=lambda x: os.path.basename(x))

    if not sorted_file_list:
        print(f"在 {directory_path} 找不到符合 {file_pattern} 的檔案。")
        return

    # Initialize size outside the loop
    size = None
    f = max(1, int(30 * fps))
    print("f: ", f)
    for filename in sorted_file_list:
        print('filename: ', filename)
        img = cv2.imread(filename)
        if img is None:
            continue
        height, width, layers = img.shape
        size = (width, height)

        for i in range(0, f):
            img_array.append(img.copy())

    # 如果啟用 loop，則加入倒序的圖片
    if loop:
        lens = len(sorted_file_list)
        for i, filename in enumerate(reversed(sorted_file_list)):
            if i == 0:
                continue
            if i == lens - 1:
                continue
            print('filename: ', filename)
            img = cv2.imread(filename)
            if img is None:
                continue
            for _ in range(0, f):
                img_array.append(img.copy())

    if not img_array:
        print("沒有有效的圖片可合成影片。")
        return

    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    out_path = os.path.join(downloads_dir, f"{name}.mp4")
    print('out_path: ', out_path)
    print("size: ", size)
    out = cv2.VideoWriter(out_path, fourcc, 30, size)
    
    for i in range(len(img_array)):
        out.write(img_array[i])
    out.release()
    print(f"影片生成成功：{out_path}")



if __name__ == "__main__":
    # 使用 argparse 解析命令行參數
    parser = argparse.ArgumentParser(description='將資料夾內的圖片序列轉換為 MP4 影片')
    parser.add_argument('-n', '-d', '-name', '--name', dest='name', type=str, required=True, help='Downloads 資料夾下的子目錄名稱')
    parser.add_argument('-f', '-fps', '--f', '--fps', dest='fps', type=float, default=0.2, help='每張照片顯示秒數 (預設 0.2 秒)')
    parser.add_argument('-p', '-pt', '--pattern', dest='pattern', type=str, default='*.jpg', help='檔名匹配模式 (預設 *.jpg)')
    parser.add_argument('-l', '-lp', '--loop', dest='loop', action='store_true', help='啟用往返迴圈效果 (Boomerang)')
    args = parser.parse_args()

    # 呼叫主函數，將解析後的參數傳入
    main(args.name, args.fps, args.pattern, args.loop)