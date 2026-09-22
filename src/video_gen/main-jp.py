import os 
import glob
import argparse

def generate_video(path1=None, frame_rate1=20, output_name='video1.mp4'):
    import cv2
    if path1 is None:
        path1 = os.path.expanduser("~/Downloads/")
    if not path1.endswith('/'):
        path1 += '/'

    a1 = glob.glob(path1 + "*.jpg")
    if not a1:
        print(f"在 {path1} 找不到任何 jpg 圖片。")
        return

    img1 = cv2.imread(a1[0]) 
    if img1 is None:
        print("無法讀取第一張圖片！")
        return

    Y1, X1, channels1 = img1.shape[:3] 

    file1 = os.path.join(path1, output_name)
    fourcc = cv2.VideoWriter_fourcc('m','p','4','v') 
    video1 = cv2.VideoWriter(file1, fourcc, frame_rate1, (X1, Y1))

    for file0 in a1:
        img1 = cv2.imread(file0)
        if img1 is None: 
            print(f"無法讀取: {file0}") 
        else: 
            img1 = cv2.resize(img1, (X1, Y1)) 
            video1.write(img1)

    video1.release()
    print(f"處理完成！影片儲存於：{file1}")

if __name__ == "__main__":
    default_path = os.path.expanduser("~/Downloads/")
    parser = argparse.ArgumentParser(description="圖片序列轉 MP4 影片工具 (jp)")
    parser.add_argument('-p', '-d', '--path', default=default_path, help='圖片資料夾路徑 (預設 ~/Downloads/)')
    parser.add_argument('-r', '-fps', '--fps', type=int, default=20, help='影片幀率 fps (預設 20)')
    parser.add_argument('-o', '--out', default='video1.mp4', help='輸出影片檔名 (預設 video1.mp4)')
    args = parser.parse_args()

    generate_video(path1=args.path, frame_rate1=args.fps, output_name=args.out)