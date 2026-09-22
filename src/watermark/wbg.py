import os
import re
import argparse
from PIL import Image, ImageDraw, ImageFont
import exifread  # type: ignore
from AppKit import NSOpenPanel, NSApplication  # type: ignore


def askdirectory(title="選擇資料夾"):
    """使用 macOS 原生對話框選擇資料夾（避免 Tcl/Tk 在部分 macOS 建置上的相容性問題）"""
    app = NSApplication.sharedApplication()
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setCanChooseFiles_(False)
    panel.setCanChooseDirectories_(True)
    panel.setAllowsMultipleSelection_(False)
    result = panel.runModal()
    if result == 1:  # NSModalResponseOK
        urls = panel.URLs()
        if urls:
            return str(urls[0].path())
    return ""

def askopenfilenames(title="選擇圖片"):
    """使用 macOS 原生對話框多選圖片檔案"""
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

DEFAULT_LONG_SIDE = 3000
BORDER_WIDTH = 240
# 與「長邊 3000、每邊 240px 白邊」等價的比例（內容區約為畫布的 1 - 此值）
DEFAULT_BORDER_RATIO = (2 * BORDER_WIDTH) / DEFAULT_LONG_SIDE

def parse_border_ratio(value):
    """白邊比例 0～1：0 無白邊，1 幾乎全為白邊（圖極小）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("白邊比例必須為數字") from None
    if not 0.0 <= v <= 1.0:
        raise argparse.ArgumentTypeError("白邊比例須在 0 到 1 之間（含）")
    return v

def is_photo_already_processed(img_path, output_size="3000"):
    """檢查照片是否已經被wbg.py處理過"""
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            if output_size != "max":
                if max(w, h) != int(output_size):
                    return False
            width, height = w, h
            corners = [
                img.getpixel((0, 0)),
                img.getpixel((width - 1, 0)),
                img.getpixel((0, height - 1)),
                img.getpixel((width - 1, height - 1)),
            ]
            white_corners = 0
            for corner in corners:
                if len(corner) >= 3:
                    r, g, b = corner[:3]
                    if r >= 250 and g >= 250 and b >= 250:
                        white_corners += 1
            if white_corners >= 3:
                return True
        return False
    except Exception as e:
        print(f"檢查照片 {img_path} 時發生錯誤: {e}")
        return False

def select_lens_manually():
    """在控制台中讓用戶選擇鏡頭"""
    available_lenses = [
        "HELIOS 44M-5 MC 58mm f/2",
        "7Artisans 7.5mm F2.8"
    ]
    
    print("\n無法從EXIF數據讀取鏡頭信息，請手動選擇鏡頭：")
    for i, lens in enumerate(available_lenses, 1):
        print(f"{i}. {lens}")
    
    while True:
        try:
            choice = input("請輸入選項編號 (1-2): ").strip()
            if choice in ['1', '2']:
                return available_lenses[int(choice) - 1]
            else:
                print("請輸入有效的選項編號 (1 或 2)")
        except KeyboardInterrupt:
            print("\n程序被用戶中斷")
            return "Unknown Lens"
        except:
            print("請輸入有效的選項編號 (1 或 2)")

def get_camera_info(img_path, lens_choice=None):
    """讀取圖片的EXIF數據，獲取相機型號和鏡頭信息"""
    try:
        with open(img_path, 'rb') as f:
            tags = exifread.process_file(f)
            
        # 獲取相機型號
        camera_make = str(tags.get('Image Make', ''))
        camera_model = str(tags.get('Image Model', ''))
        
        # 獲取鏡頭信息
        lens_make = str(tags.get('EXIF LensMake', ''))
        lens_model = str(tags.get('EXIF LensModel', ''))
        
        # 組合相機信息
        camera_info = f"{camera_make} {camera_model}".strip()
        if not camera_info:
            camera_info = "Unknown Camera"
            
        # 組合鏡頭信息
        lens_info = f"{lens_make} {lens_model}".strip()
        if not lens_info:
            # 如果沒有鏡頭型號，嘗試從焦距信息獲取
            focal_length = str(tags.get('EXIF FocalLength', ''))
            if focal_length:
                lens_info = f"{focal_length}mm"
            else:
                # 如果都無法獲取，使用用戶選擇的鏡頭或提示選擇
                if lens_choice:
                    lens_info = lens_choice
                else:
                    lens_info = select_lens_manually()
        
        # 檢查最終的相機/鏡頭信息中是否包含無效的光圈值
        camera_lens_info = f"{camera_info} / {lens_info}"
        
        # 如果鏡頭信息只有焦距且光圈值無效，觸發手動選擇
        if "mm" in lens_info and "f/--" in camera_lens_info:
            if lens_choice:
                lens_info = lens_choice
            else:
                lens_info = select_lens_manually()
            camera_lens_info = f"{camera_info} / {lens_info}"
        
        return camera_lens_info
        
    except Exception as e:
        print(f"無法讀取 {img_path} 的EXIF數據: {e}")
        if lens_choice:
            return f"Unknown Camera / {lens_choice}"
        else:
            lens_info = select_lens_manually()
            return f"Unknown Camera / {lens_info}"

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")

def parse_aspect_option(s):
    """解析 --aspect：auto（與原圖同比例／同直橫向）、square／1:1、或寬高比如 4:3、16:9。"""
    if s is None:
        return "auto", None
    t = s.strip().lower()
    if t in ("auto", ""):
        return "auto", None
    if t in ("square", "1:1", "1-1"):
        return "fixed", (1, 1)
    m = re.fullmatch(r"(\d+)\s*:\s*(\d+)", t)
    if not m:
        raise argparse.ArgumentTypeError(
            "無效的 --aspect，請用 auto、square、1:1 或 寬:高（例如 4:3、16:9）"
        )
    aw, ah = int(m.group(1)), int(m.group(2))
    if aw <= 0 or ah <= 0:
        raise argparse.ArgumentTypeError("比例數值必須為正整數")
    return "fixed", (aw, ah)

def compute_canvas_size(orig_w, orig_h, aspect_mode, ratio_tuple, target_size):
    """長邊固定為 target_size，寬高比由模式決定；fixed 時直向會自動交換寬高。"""
    L = target_size
    if orig_w <= 0 or orig_h <= 0:
        return L, L
    if aspect_mode == "auto":
        if orig_w >= orig_h:
            return L, max(1, int(round(L * orig_h / orig_w)))
        return max(1, int(round(L * orig_w / orig_h))), L
    aw, ah = ratio_tuple
    if orig_w >= orig_h:
        return L, max(1, int(round(L * ah / aw)))
    return max(1, int(round(L * aw / ah))), L

def collect_image_paths_from_folder(input_folder):
    paths = []
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(_IMAGE_EXTS):
            paths.append(os.path.join(input_folder, filename))
    return paths

def add_white_background(
    image_paths,
    output_folder,
    default_lens=None,
    add_text=True,
    aspect_mode="auto",
    aspect_ratio=None,
    border_ratio=DEFAULT_BORDER_RATIO,
    border_equal=False,
    output_size="3000",
):
    # 确保输出文件夹存在
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for img_path in image_paths:
        filename = os.path.basename(img_path)
        if not os.path.isfile(img_path):
            print(f"跳過 {filename}：不是有效檔案")
            continue
        if not filename.lower().endswith(_IMAGE_EXTS):
            print(f"跳過 {filename}：不支援的圖片格式")
            continue

        if is_photo_already_processed(img_path, output_size):
            print(f"跳過 {filename}：照片已經被處理過（包含白邊）")
            continue

        img = Image.open(img_path)
        exif_data = img.info.get('exif')
        icc_profile = img.info.get('icc_profile')
        
        # 尋找並保留額外的元資料 (例如 XMP, IPTC 等 APP segments)
        extra_markers = []
        if hasattr(img, 'applist'):
            for marker, data in img.applist:
                if marker == 'APP0': 
                    continue
                if marker == 'APP1' and data.startswith(b'Exif\x00\x00'):
                    continue
                if marker == 'APP2' and data.startswith(b'ICC_PROFILE\x00'):
                    continue
                if marker == 'APP14' and data.startswith(b'Adobe\x00'):
                    continue
                
                if isinstance(marker, str) and marker.startswith('APP'):
                    try:
                        marker_code = 0xE0 + int(marker[3:])
                        size = len(data) + 2
                        marker_bytes = bytes([0xFF, marker_code]) + size.to_bytes(2, 'big') + data
                        extra_markers.append(marker_bytes)
                    except:
                        pass
        extra_data = b''.join(extra_markers)

        # 讀取相機和鏡頭信息（僅在需要添加文字時）
        camera_info = ""
        if add_text:
            camera_info = get_camera_info(img_path, default_lens)
            print(f"處理 {filename}: {camera_info}")
        else:
            print(f"處理 {filename}: 僅添加白邊，不添加文字")

        orig_w, orig_h = img.size
        
        if output_size == "max":
            target_size = max(orig_w, orig_h)
        else:
            target_size = int(output_size)
            
        if border_equal:
            border_px = int(round(target_size * border_ratio / 2))
            
            if aspect_mode == "auto":
                inner_long = max(1, target_size - 2 * border_px)
                if orig_w >= orig_h:
                    new_w = inner_long
                    new_h = max(1, int(round(inner_long * orig_h / orig_w)))
                else:
                    new_h = inner_long
                    new_w = max(1, int(round(inner_long * orig_w / orig_h)))
                
                canvas_w = new_w + 2 * border_px
                canvas_h = new_h + 2 * border_px
                
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                new_img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
                x = border_px
                y = border_px
                new_img.paste(img, (x, y))
            else:
                canvas_w, canvas_h = compute_canvas_size(orig_w, orig_h, aspect_mode, aspect_ratio)
                inner_w = max(1, canvas_w - 2 * border_px)
                inner_h = max(1, canvas_h - 2 * border_px)
                
                if inner_w < 1 or inner_h < 1:
                    print(f"跳過 {filename}：畫布比例下內部區域過小，請降低 --border-ratio 或調整 --aspect")
                    img.close()
                    continue
                
                scale = min(inner_w / orig_w, inner_h / orig_h)
                new_w = max(1, int(round(orig_w * scale)))
                new_h = max(1, int(round(orig_h * scale)))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                new_img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
                x = (canvas_w - new_w) // 2
                y = (canvas_h - new_h) // 2
                new_img.paste(img, (x, y))
        else:
            canvas_w, canvas_h = compute_canvas_size(
                orig_w, orig_h, aspect_mode, aspect_ratio, target_size
            )
            # 內容區為畫布的 (1 - border_ratio)；0 無白邊，1 時內容區收斂為至少 1px
            inner_w = max(1, int(round(canvas_w * (1.0 - border_ratio))))
            inner_h = max(1, int(round(canvas_h * (1.0 - border_ratio))))
            if inner_w < 1 or inner_h < 1:
                print(f"跳過 {filename}：畫布比例下內部區域過小，請降低 --border-ratio 或調整 --aspect")
                img.close()
                continue

            scale = min(inner_w / orig_w, inner_h / orig_h)
            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            new_img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
            x = (canvas_w - new_w) // 2
            y = (canvas_h - new_h) // 2
            new_img.paste(img, (x, y))

        # 添加相機和鏡頭信息文字（僅在需要時）
        if add_text and camera_info:
            draw = ImageDraw.Draw(new_img)

            # 嘗試使用系統字體，如果沒有則使用默認字體
            try:
                # 在macOS上嘗試使用Didot
                font = ImageFont.truetype("/Library/Fonts/SF-Mono-MediumItalic.otf", 44)
            except:
                try:
                    # 嘗試其他常見的襯線體字體
                    font = ImageFont.truetype("/System/Library/Fonts/Georgia.ttf", 44)
                except:
                    try:
                        # 最後嘗試使用默認字體
                        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 44)
                    except:
                        # 如果都失敗，使用PIL默認字體
                        font = ImageFont.load_default()

            # 計算文字位置（下方中間，離底部50px）
            text_bbox = draw.textbbox((0, 0), camera_info, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            text_x = (canvas_w - text_width) // 2
            text_y = canvas_h - 50 - text_height

            # 繪製文字（黑色）
            draw.text((text_x, text_y), camera_info, fill=(5, 5, 5), font=font)

        save_kwargs = {}
        if exif_data:
            save_kwargs['exif'] = exif_data
        if icc_profile:
            save_kwargs['icc_profile'] = icc_profile
        if extra_data:
            save_kwargs['extra'] = extra_data

        new_img.save(os.path.join(output_folder, filename), **save_kwargs)

    print(f'处理完成！所有图片已保存到: {output_folder}')

def main(
    add_text=False,
    pick_files=False,
    aspect_mode="auto",
    aspect_ratio=None,
    border_ratio=DEFAULT_BORDER_RATIO,
    border_equal=False,
    output_size="3000",
):
    if pick_files:
        image_paths = askopenfilenames(title="選擇要處理的圖片（可多選）")
        if not image_paths:
            print("未選擇圖片，程序結束。")
            return
    else:
        input_folder = askdirectory(title="选择输入文件夹")
        if not input_folder:
            print("未选择输入文件夹，程序结束。")
            return
        image_paths = collect_image_paths_from_folder(input_folder)
        if not image_paths:
            print("輸入資料夾中沒有支援的圖片檔案，程序結束。")
            return

    # 选择输出文件夹
    output_folder = askdirectory(title='选择输出文件夹')
    if not output_folder:
        print("未选择输出文件夹，程序结束。")
        return

    default_lens = None
    
    # 只有在需要添加文字時才詢問鏡頭設定
    if add_text:
        # 詢問用戶是否要預設一個鏡頭
        print("\n是否要為所有照片預設一個鏡頭？")
        print("如果照片無法從EXIF讀取鏡頭信息，將使用預設鏡頭")
        print("1. 是，預設一個鏡頭")
        print("2. 否，每張照片都手動選擇")
        
        while True:
            try:
                preset_choice = input("請選擇 (1/2): ").strip()
                if preset_choice == '1':
                    default_lens = select_lens_manually()
                    print(f"已設定預設鏡頭: {default_lens}")
                    break
                elif preset_choice == '2':
                    default_lens = None
                    print("將為每張照片手動選擇鏡頭")
                    break
                else:
                    print("請輸入 1 或 2")
            except KeyboardInterrupt:
                print("\n程序被用戶中斷")
                return
            except:
                print("請輸入 1 或 2")
    else:
        print("\n已設定為僅添加白邊，不添加文字標記")

    add_white_background(
        image_paths,
        output_folder,
        default_lens,
        add_text,
        aspect_mode=aspect_mode,
        aspect_ratio=aspect_ratio,
        border_ratio=border_ratio,
        border_equal=border_equal,
        output_size=output_size,
    )

def show_help():
    """顯示使用說明"""
    help_text = """
=== wbg.py 使用說明書 ===

功能概述：
wbg.py 是一個照片處理工具，可以為照片添加白色背景邊框、讀取相機和鏡頭信息，
並在照片上添加相機/鏡頭文字標記。

主要功能：
1. 自動為照片添加白色邊框（長邊 3000 像素，寬高比可由 --aspect 控制；預設與原圖同比例）
2. 讀取照片的EXIF數據獲取相機和鏡頭信息
3. 在照片下方添加相機/鏡頭文字（英文襯線體，44號字體）
4. 智能跳過已處理過的照片
5. 支持手動選擇鏡頭（當EXIF數據不完整時）

使用方法：
1. 基本使用（僅添加白邊，不加文字）：
   python3 wbg.py

2. 添加白邊和相機信息文字：
   python3 wbg.py --add-text

3. 只處理選取的圖片（不選輸入資料夾，可多選檔案）：
   python3 wbg.py --pick-files
   python3 wbg.py --pick-files --add-text

4. 成品比例（預設 auto＝與原圖同比例、同直橫向）：
   python3 wbg.py --aspect auto
   python3 wbg.py --aspect square
   python3 wbg.py --aspect 4:3
   python3 wbg.py --aspect 16:9

5. 白邊比例 0～1（0＝無白邊，1＝幾乎全白；預設約 0.16，約等同長邊 3000 時每邊 240px）：
   python3 wbg.py --border-ratio 0
   python3 wbg.py --border-ratio 1
   python3 wbg.py --border-ratio 0.16

6. 等比邊框（四邊白邊像素相等，比例依照長邊計算，預設 false）：
   python3 wbg.py --border-equal

7. 查看幫助：
   python3 wbg.py --help          # 顯示基本幫助
   python3 wbg.py --manual-help   # 顯示詳細使用說明

8. 查看版本：
   python3 wbg.py --version

使用流程：
1. 運行程序後，選擇包含原始照片的輸入資料夾；若使用 --pick-files，則改為多選圖片檔案
2. 選擇處理後照片的輸出資料夾
3. 如果使用 --add-text 參數，會詢問鏡頭設定方式：
   - 選項1：為所有照片預設一個鏡頭（推薦用於批量處理）
   - 選項2：每張照片都手動選擇鏡頭
4. 如果選擇預設鏡頭，從以下兩個選項中選擇：
   - HELIOS 44M-5 MC 58mm f/2
   - 7Artisans 7.5mm F2.8
5. 程序會自動處理所有照片並顯示進度

輸出規格：
- 畫布長邊：3000 像素；寬高比：--aspect auto（與原圖一致）或 square／1:1／4:3／16:9 等
- 白邊：--border-ratio 0～1；內容區寬高為畫布的 (1−比例)，圖片在內容區內等比置中；0 無白邊，1 內容區收斂為 1px（幾乎全白）
- 文字設定（僅在使用 --add-text 時）：
  - 文字位置：底部中央，離底部50px
  - 文字字體：SF Mono Medium Italic（44號）或備用字體
  - 文字顏色：深灰色 (5,5,5)

支持的照片格式：
- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- BMP (.bmp)

智能功能：
- 自動檢測已處理照片並跳過
- 識別光圈值為 f/-- 的情況並觸發手動選擇
- 支持現代數碼相機和手動鏡頭的EXIF數據

虛擬環境使用（推薦）：
1. 創建虛擬環境：python3 -m venv venv
2. 啟動虛擬環境：
   - macOS/Linux: source venv/bin/activate
   - Windows: venv\\Scripts\\activate
3. 安裝依賴：pip install -r requirements.txt
4. 運行程序：python3 wbg.py
5. 退出環境：deactivate

注意事項：
1. 確保已安裝必要的依賴庫：pip install Pillow exifread
2. 處理大量照片時建議預設鏡頭以提高效率
3. 程序會自動跳過已處理過的照片，可以安全地重新運行

技術支持：
如有問題，請檢查：
1. 照片是否包含EXIF數據
2. 依賴庫是否正確安裝
3. 輸入輸出資料夾權限是否正確
"""
    print(help_text)

def show_version():
    """顯示版本信息"""
    print("wbg.py 版本 1.0")
    print("照片處理工具 - 添加白邊和相機信息標記")

if __name__ == "__main__":
    # 解析命令行參數
    parser = argparse.ArgumentParser(description="照片處理工具 - 添加白邊和相機信息標記")
    parser.add_argument('-H', '-mh', '--manual-help', action='store_true', help='顯示詳細使用說明')
    parser.add_argument('-v', '--version', action='store_true', help='顯示版本信息')
    parser.add_argument('-t', '-tx', '--add-text', dest='add_text', action='store_true', help='在照片上添加相機和鏡頭信息文字（預設不加文字）')
    parser.add_argument('-p', '-pf', '--pick-files', dest='pick_files', action='store_true', help='用檔案選擇器多選圖片處理，不選輸入資料夾')
    parser.add_argument(
        '-a', '-ar', '--aspect',
        dest='aspect',
        type=parse_aspect_option,
        default=parse_aspect_option("auto"),
        metavar="MODE",
        help='畫布比例：auto(預設)、1:1、或 4:3 等',
    )
    parser.add_argument(
        '-b', '-br', '--border-ratio',
        dest='border_ratio',
        type=parse_border_ratio,
        default=DEFAULT_BORDER_RATIO,
        metavar="0-1",
        help='白邊佔畫布比例：0 無白邊、1 幾乎全白；預設約 0.16（約等同長邊 3000 時每邊 240px）',
    )
    parser.add_argument(
        '-e', '-be', '--border-equal',
        dest='border_equal',
        action='store_true',
        help='四邊白邊像素相等，比例依照長邊計算',
    )
    parser.add_argument(
        '-s', '-sz', '--size',
        dest='output_size',
        default='3000',
        help='設定長邊尺寸，預設 3000。輸入 "max" 則依照原圖尺寸'
    )
    parser.add_argument('--x', action='store_true', help='套用 X(Twitter) 預設：選取檔案、白邊 0.05、等寬白邊')
    parser.add_argument('--ig', action='store_true', help='套用 IG 預設：選取檔案、1:1 比例、白邊 0.16')

    args = parser.parse_args()

    # 處理預設參數組合
    if args.x:
        args.pick_files = True
        args.border_ratio = 0.05
        args.border_equal = True
    if args.ig:
        args.pick_files = True
        args.aspect = parse_aspect_option("1:1")
        args.border_ratio = 0.16

    if args.manual_help:
        show_help()
    elif args.version:
        show_version()
    else:
        amode, aratio = args.aspect
        main(
            add_text=args.add_text,
            pick_files=args.pick_files,
            aspect_mode=amode,
            aspect_ratio=aratio,
            border_ratio=args.border_ratio,
            border_equal=args.border_equal,
            output_size=args.output_size,
        )
