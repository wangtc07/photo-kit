import os
from PIL import Image
from AppKit import NSOpenPanel, NSApplication  # type: ignore
import argparse
import crop_web_ui

def askopenfilenames(title="選擇圖片"):
    app = NSApplication.sharedApplication()
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(True)
    panel.setAllowedFileTypes_(["png", "jpg", "jpeg", "gif", "bmp"])
    result = panel.runModal()
    if result == 1:
        urls = panel.URLs()
        if urls:
            return [str(u.path()) for u in urls]
    return []

def main():
    parser = argparse.ArgumentParser(description="合併多張照片為一張，自動調整排版並加上白邊")
    parser.add_argument('-b', '--border-ratio', dest='border_ratio', type=float, default=0.05, help='白邊與間隔比例 (預設 0.05)')
    parser.add_argument('-l', '--long-side', dest='long_side', type=int, default=3000, help='單張圖片對應的基準長邊 (預設 3000)')
    parser.add_argument('-c', '--crop', dest='crop', action='store_true', help='啟用 Web UI 裁切功能 (設定將套用至所有照片)')
    parser.add_argument('-o', '--order', dest='order', choices=['name', 'select'], default='name', help='照片排列順序：name 為檔名順序 (預設)，select 為選取/輸入順序')
    parser.add_argument('files', nargs='*', help='要處理的圖片檔案路徑 (若不提供則會跳出選擇視窗)')
    args = parser.parse_args()

    # wbg.py 的白邊設定邏輯
    OUTPUT_LONG_SIDE = args.long_side
    BORDER_WIDTH = int(OUTPUT_LONG_SIDE * args.border_ratio / 2)
    INNER_LONG = int(OUTPUT_LONG_SIDE * (1 - args.border_ratio))

    # 間距也依照 wbg 的設定一樣
    GAP = BORDER_WIDTH
    MARGIN = BORDER_WIDTH

    if args.files:
        image_paths = [os.path.abspath(f) for f in args.files]
    else:
        print("請選擇要合併的照片（可多選）...")
        image_paths = askopenfilenames(title="選擇要合併的照片 (多選)")
        
    if not image_paths:
        print("未選擇圖片，程序結束。")
        return
        
    if args.order == 'name':
        # 依照檔名順序排列
        image_paths.sort(key=lambda x: os.path.basename(x))
    # 若為 'select'，則保持原來的選擇/輸入順序
    
    print(f"共選擇了 {len(image_paths)} 張照片，正在處理...")
    
    crop_box = None
    if args.crop:
        print("準備開啟 Web 裁切介面...")
        crop_box = crop_web_ui.start_crop_review(image_paths[0])
        if not crop_box:
            print("裁切取消，將使用原圖處理。")
    
    # 讀取並縮放圖片
    processed_images = []
    for path in image_paths:
        try:
            img = Image.open(path)
            # 轉換為RGB以防是RGBA
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # 套用裁切
            if crop_box:
                x = max(0, int(crop_box['x']))
                y = max(0, int(crop_box['y']))
                w = int(crop_box['width'])
                h = int(crop_box['height'])
                
                # 防呆：確保裁切範圍不超出圖片
                right = min(img.width, x + w)
                bottom = min(img.height, y + h)
                
                img = img.crop((x, y, right, bottom))
            
            orig_w, orig_h = img.size
            scale = INNER_LONG / max(orig_w, orig_h)
            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            processed_images.append((new_w, new_h, img))
        except Exception as e:
            print(f"無法讀取或處理圖片 {path}: {e}")
            
    if not processed_images:
        print("沒有成功處理任何圖片。")
        return
        
    n = len(processed_images)
    
    # 計算欄數
    if n == 4 or n <= 2:
        max_cols = 2
    else:
        max_cols = 3
        
    # 取得最大的儲存格尺寸
    cell_w = max(w for w, h, img in processed_images)
    cell_h = max(h for w, h, img in processed_images)
    
    # 將圖片分裝到行中
    rows = []
    for i in range(0, n, max_cols):
        rows.append(processed_images[i:i+max_cols])
        
    total_rows = len(rows)
    actual_cols = min(n, max_cols)
    
    # 計算畫布大小
    canvas_w = 2 * MARGIN + actual_cols * cell_w + (actual_cols - 1) * GAP
    canvas_h = 2 * MARGIN + total_rows * cell_h + (total_rows - 1) * GAP
    
    new_img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    
    for r, row in enumerate(rows):
        # 計算此行的寬度
        row_cols = len(row)
        row_w = row_cols * cell_w + (row_cols - 1) * GAP
        
        # 水平置中此行
        start_x = MARGIN + (canvas_w - 2 * MARGIN - row_w) // 2
        start_y = MARGIN + r * (cell_h + GAP)
        
        for c, img_data in enumerate(row):
            w, h, img = img_data
            
            # 儲存格的左上角
            cell_x = start_x + c * (cell_w + GAP)
            cell_y = start_y
            
            # 圖片在儲存格內置中
            img_x = cell_x + (cell_w - w) // 2
            img_y = cell_y + (cell_h - h) // 2
            
            new_img.paste(img, (img_x, img_y))
            
    # 輸出到與第一張照片相同資料夾
    output_dir = os.path.dirname(image_paths[0])
    base_name = f"combined_{n}_photos"
    extension = ".jpg"
    
    counter = 1
    while True:
        output_name = f"{base_name}_{counter:03d}{extension}"
        output_path = os.path.join(output_dir, output_name)
        if not os.path.exists(output_path):
            break
        counter += 1
            
    new_img.save(output_path, quality=100)
    print(f"合併完成！已儲存至: {output_path}")

if __name__ == "__main__":
    main()
