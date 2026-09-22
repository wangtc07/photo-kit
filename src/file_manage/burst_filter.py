#!/usr/bin/env python3
import os
import shutil
import sqlite3
import collections
import re
import argparse
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

def calculate_dhash(image_path, hash_size=8):
    """計算圖片的 dHash (Difference Hash)"""
    try:
        with Image.open(image_path) as img:
            # 轉灰階並縮放成 (hash_size + 1) x hash_size
            img = img.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            
            diff = []
            for row in range(hash_size):
                for col in range(hash_size):
                    pixel_left = img.getpixel((col, row))
                    pixel_right = img.getpixel((col + 1, row))
                    diff.append(pixel_left > pixel_right)
                    
            decimal_value = 0
            for i, val in enumerate(diff):
                if val:
                    decimal_value += 2**i
            return decimal_value
    except Exception as e:
        print(f"警告: 無法讀取圖片以計算 hash {image_path}: {e}")
        return None

def hamming_distance(h1, h2):
    """計算兩個 hash 之間的 Hamming Distance"""
    if h1 is None or h2 is None:
        return 999
    return bin(h1 ^ h2).count('1')

def get_file_num(basename):
    match = re.search(r'(\d+)', basename)
    return int(match.group(1)) if match else 0

def get_c1_ratings(db_path, folder_path):
    """取得 Capture One 資料庫中的所有星等資訊"""
    if not os.path.exists(db_path):
        print(f"找不到 Capture One 資料庫: {db_path}")
        return {}
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    rel_path = folder_path.strip("/")
    
    # 加入 ZPATHLOCATION 過濾，確保只抓到這個資料夾內的照片，避免同名檔案干擾
    query = """
    SELECT i.ZIMAGEFILENAME, i.Z_PK, m.ZBASIC_RATING 
    FROM ZIMAGE i
    JOIN ZVARIANT v ON v.ZIMAGE = i.Z_PK
    JOIN ZVARIANTMETADATA m ON (m.ZLAYER = v.ZDEFAULTLAYER OR m.ZLAYER = v.ZADJUSTMENTLAYER)
    JOIN ZPATHLOCATION p ON i.ZIMAGELOCATION = p.Z_PK
    WHERE p.ZRELATIVEPATH = ?
    """
    try:
        cursor.execute(query, (rel_path,))
    except Exception as e:
        print(f"資料庫查詢錯誤: {e}")
        return {}

    db_info = collections.defaultdict(list)
    for row in cursor.fetchall():
        filename, pk, rating = row
        if filename:
            name, _ = os.path.splitext(filename)
            db_info[name].append((pk, rating))
            
    # 取所有變體/紀錄中的最高星等
    # 若一張照片有多個變體，只要其中一個變體(包含調整圖層)有星等就保留
    ratings = {}
    for name, records in db_info.items():
        max_rating = max([r for pk, r in records if r is not None] + [0])
        ratings[name] = max_rating
    return ratings

def process_bursts(folder, c1_db_path, time_threshold=3, hash_threshold=15, trash_dir_name="trash", dry_run=False):
    """
    主要處理邏輯：
    1. 掃描資料夾內的 JPG
    2. 使用時間 + 影像視覺相似度 (dHash) 分組
    3. 查詢 C1 星等，丟棄沒星等的廢片
    """
    trash_folder = os.path.join(folder, trash_dir_name)
    if not dry_run and not os.path.exists(trash_folder):
        os.makedirs(trash_folder)
        
    print(f"正在掃描資料夾: {folder} ...")
    basenames = set()
    for f in os.listdir(folder):
        file_path = os.path.join(folder, f)
        # 只處理當前資料夾的檔案，忽略子資料夾
        if os.path.isfile(file_path) and f.upper().endswith(('.JPG', '.RAF', '.DNG')):
            name, _ = os.path.splitext(f)
            basenames.add(name)
            
    if not basenames:
        print("資料夾中沒有找到 JPG, RAF 或 DNG 檔案。")
        return

    print(f"正在從 Capture One 讀取星等資訊...")
    c1_ratings = get_c1_ratings(c1_db_path, folder)

    print(f"正在分析 {len(basenames)} 張照片的拍攝時間與影像特徵 (這可能需要幾秒鐘)...")
    basename_info = {}
    for b in basenames:
        # Get modification time
        jpg_path = os.path.join(folder, b + ".JPG")
        raf_path = os.path.join(folder, b + ".RAF")
        dng_path = os.path.join(folder, b + ".DNG")
        
        target_path = jpg_path if os.path.exists(jpg_path) else (raf_path if os.path.exists(raf_path) else (dng_path if os.path.exists(dng_path) else None))
        if not target_path:
            continue
            
        t = os.path.getmtime(target_path)
        
        # 只對 JPG 計算 hash (比較快)，沒有 JPG 就不算 hash (回傳 None)
        dhash = calculate_dhash(jpg_path) if os.path.exists(jpg_path) else None
        
        r = c1_ratings.get(b, 0)
        basename_info[b] = {'time': t, 'hash': dhash, 'rating': r}

    # 排序檔案以利分組
    sorted_bases = sorted(list(basename_info.keys()), key=lambda x: get_file_num(x))
    
    bursts = []
    current_burst = []

    for b in sorted_bases:
        if not current_burst:
            current_burst.append(b)
            continue
        
        prev_b = current_burst[-1]
        num_diff = get_file_num(b) - get_file_num(prev_b)
        time_diff = abs(basename_info[b]['time'] - basename_info[prev_b]['time'])
        h_dist = hamming_distance(basename_info[b]['hash'], basename_info[prev_b]['hash'])
        
        # 精準連拍條件：
        # 1. 檔名相近 (連續)
        # 2. 時間極為接近 (<= 3秒)
        # 3. 視覺極為相似 (h_dist <= hash_threshold) - 確保同秒內的兩組不同運鏡不會被混在一起
        is_burst = (0 < num_diff <= 3) and (time_diff <= time_threshold) and (h_dist <= hash_threshold)
        
        if is_burst:
            current_burst.append(b)
        else:
            if len(current_burst) > 1:
                bursts.append(current_burst)
            current_burst = [b]

    if len(current_burst) > 1:
        bursts.append(current_burst)

    print(f"\n分析完成！共找到 {len(bursts)} 組連拍。")
    
    moved_count = 0
    for i, burst in enumerate(bursts):
        ratings = [basename_info[b]['rating'] for b in burst]
        max_rating = max(ratings)
        
        if max_rating >= 1:
            print(f"\n[Group {i+1}] {burst}")
            print("  -> 偵測到有標記星等的照片，準備清理未標記的照片...")
            for b in burst:
                r = basename_info[b]['rating']
                if r < 1:
                    for ext in ['.JPG', '.RAF', '.DNG', '.jpg', '.raf', '.dng']:
                        src = os.path.join(folder, b + ext)
                        if os.path.exists(src):
                            if not dry_run:
                                shutil.move(src, os.path.join(trash_folder, b + ext))
                            moved_count += 1
                            print(f"  🗑️  移除: {b+ext}")
                else:
                    print(f"  ⭐ 保留: {b} (星等: {r})")
        else:
            print(f"\n[Group {i+1}] {burst}")
            print("  -> 整組都沒有星等，將全數移至 trash...")
            for b in burst:
                for ext in ['.JPG', '.RAF', '.jpg', '.raf']:
                    src = os.path.join(folder, b + ext)
                    if os.path.exists(src):
                        if not dry_run:
                            shutil.move(src, os.path.join(trash_folder, b + ext))
                        moved_count += 1
                        print(f"  🗑️  移除: {b+ext}")

    action = "模擬移動" if dry_run else "實際移動"
    print(f"\n✅ 處理完畢！共 {action} 了 {moved_count} 個檔案到 trash 資料夾。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自動辨識連拍並依照 Capture One 星等過濾廢片。")
    parser.add_argument("folders", nargs="*", help="要處理的照片資料夾路徑 (可多個)")
    parser.add_argument("-db", "--db", dest="db", default=os.path.expanduser("~/Pictures/Capture One Catalog.cocatalog/Capture One Catalog.cocatalogdb"), help="Capture One 資料庫路徑")
    parser.add_argument("-d", "-dr", "--dry-run", dest="dry_run", action="store_true", help="只列印會執行的操作，不實際移動檔案")
    parser.add_argument("-t", "-tt", "--time-threshold", dest="time_threshold", type=int, default=3, help="時間相差幾秒內算連拍 (預設 3 秒)")
    parser.add_argument("-s", "-ht", "--hash-threshold", dest="hash_threshold", type=int, default=15, help="視覺差異度閾值，越小越嚴格 (預設 15)")
    
    args = parser.parse_args()
    
    folders = args.folders
    if not folders:
        # 如果沒有輸入參數，使用 osascript (AppleScript) 彈出視窗讓使用者選擇資料夾 (可複選)
        import subprocess
        script = '''
        set folderList to choose folder with prompt "請選擇要處理的資料夾 (可複選):" with multiple selections allowed
        set pathList to {}
        repeat with aFolder in folderList
            set end of pathList to POSIX path of aFolder
        end repeat
        set AppleScript's text item delimiters to "\\n"
        return pathList as string
        '''
        try:
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, check=True)
            folders = [p for p in result.stdout.strip().split('\n') if p]
        except subprocess.CalledProcessError:
            print("未選擇資料夾，程式結束。")
            import sys
            sys.exit(0)
            
    if not folders:
        print("未選擇資料夾，程式結束。")
        import sys
        sys.exit(0)
        
    for folder in folders:
        print(f"\n{'='*60}")
        print(f"開始處理資料夾: {folder}")
        print(f"{'='*60}")
        process_bursts(
            folder=folder, 
            c1_db_path=args.db, 
            time_threshold=args.time_threshold, 
            hash_threshold=args.hash_threshold,
            dry_run=args.dry_run
        )
