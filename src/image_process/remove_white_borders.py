#!/usr/bin/env python3
"""
批次去除圖片白邊工具
自動偵測圖片外圍的白色或近白色邊框並裁切，輸出至該資料夾的子資料夾中。
支援原生資料夾選取、JPEG 噪點容差門檻、EXIF 保留與底部獨立浮水印排除。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image

# 支援的圖片格式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
# 預設輸出子資料夾名稱
DEFAULT_OUTPUT_SUBFOLDER = "trimmed"
# 預設白邊色彩門檻 (0-255，RGB 皆大於等於此值視為白色)
DEFAULT_THRESHOLD = 245
# 預設判定整行/整列為白邊的比例 (99.5% 以上像素為白色即視為白邊，抵抗 JPEG 壓縮噪點)
DEFAULT_ROW_WHITE_RATIO = 0.995


def select_folder() -> Optional[Path]:
    """使用 macOS 原生對話框選擇資料夾，若非 macOS 或失敗則退回至 Tkinter 或終端機輸入"""
    if sys.platform == "darwin":
        try:
            script = 'POSIX path of (choose folder with prompt "請選擇要去除白邊的圖片資料夾")'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(title="請選擇要去除白邊的圖片資料夾")
        root.destroy()
        if path:
            return Path(path)
    except Exception:
        pass

    try:
        raw_path = input("請輸入資料夾路徑: ").strip()
        if raw_path:
            p = Path(os.path.expanduser(raw_path))
            if p.exists() and p.is_dir():
                return p
    except KeyboardInterrupt:
        pass

    return None


def detect_content_bbox(
    img: Image.Image,
    threshold: int = DEFAULT_THRESHOLD,
    white_ratio: float = DEFAULT_ROW_WHITE_RATIO,
    ignore_watermark: bool = False,
    padding: int = 0,
) -> Tuple[int, int, int, int]:
    """
    偵測圖片中去除白邊後的主體內容範圍 (left, top, right, bottom)。
    若整張圖全為白色，回傳 (0, 0, width, height)。
    """
    w, h = img.size
    rgb_img = img.convert("RGB")
    data = np.asarray(rgb_img, dtype=np.uint8)

    # 判斷每個像素是否為白色 (R, G, B >= threshold)
    is_white = np.all(data >= threshold, axis=2)

    # 計算每一行 (row) 與每一列 (col) 白像素佔比
    row_white_ratios = np.mean(is_white, axis=1)
    col_white_ratios = np.mean(is_white, axis=0)

    # 內容行/列：白色比例小於指定比率的行/列
    row_has_content = row_white_ratios < white_ratio
    col_has_content = col_white_ratios < white_ratio

    content_rows = np.where(row_has_content)[0]
    content_cols = np.where(col_has_content)[0]

    if len(content_rows) == 0 or len(content_cols) == 0:
        # 整張圖皆判定為白邊，不裁切
        return (0, 0, w, h)

    top = int(content_rows[0])
    bottom = int(content_rows[-1]) + 1
    left = int(content_cols[0])
    right = int(content_cols[-1]) + 1

    # 若啟用 ignore_watermark，分析垂直方向的內容區塊
    # 用於排除如 wbg.py 於底部白邊添加的相機/鏡頭 EXIF 小字
    if ignore_watermark and len(content_rows) > 0:
        # 尋找垂直方向上由白邊間隔開的各個內容區塊
        diff = np.diff(np.concatenate(([0], row_has_content.astype(int), [0])))
        seg_starts = np.where(diff == 1)[0]
        seg_ends = np.where(diff == -1)[0]

        segments = list(zip(seg_starts, seg_ends))
        if len(segments) > 1:
            # 依區塊高度找出主要照片內容區塊（高度最大者）
            main_seg = max(segments, key=lambda s: s[1] - s[0])
            main_height = main_seg[1] - main_seg[0]

            # 檢查是否有位於底部且與主區塊分離的小型區塊 (如文字浮水印)
            last_seg = segments[-1]
            last_height = last_seg[1] - last_seg[0]
            gap = last_seg[0] - main_seg[1]

            # 若底部區塊很小 (例如小於主體 15% 且高度小於 150px) 且有明顯白邊間隔
            if last_seg != main_seg and gap >= 10 and last_height < min(150, main_height * 0.15):
                top = int(main_seg[0])
                bottom = int(main_seg[1])
                # 重新根據主內容區塊的行範圍計算水平邊界
                main_slice = is_white[top:bottom, :]
                slice_col_ratios = np.mean(main_slice, axis=0)
                slice_cols = np.where(slice_col_ratios < white_ratio)[0]
                if len(slice_cols) > 0:
                    left = int(slice_cols[0])
                    right = int(slice_cols[-1]) + 1

    # 加入安全邊界 (padding)
    if padding > 0:
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(w, right + padding)
        bottom = min(h, bottom + padding)

    return (left, top, right, bottom)


def process_image(
    src_path: Path,
    out_dir: Path,
    threshold: int = DEFAULT_THRESHOLD,
    ignore_watermark: bool = False,
    padding: int = 0,
    quality: int = 95,
) -> Tuple[bool, str]:
    """處理單張圖片去除白邊，並輸出至 out_dir"""
    try:
        with Image.open(src_path) as img:
            orig_w, orig_h = img.size
            bbox = detect_content_bbox(
                img,
                threshold=threshold,
                ignore_watermark=ignore_watermark,
                padding=padding,
            )
            left, top, right, bottom = bbox
            new_w = right - left
            new_h = bottom - top

            has_crop = (left > 0 or top > 0 or right < orig_w or bottom < orig_h)
            cropped_img = img.crop(bbox)

            # 準備輸出路徑 (保留原始檔名)
            out_path = out_dir / src_path.name

            # 保存設定：盡可能保留 EXIF 與 ICC Profile
            save_kwargs = {}
            exif = img.info.get("exif")
            if exif:
                save_kwargs["exif"] = exif
            icc = img.info.get("icc_profile")
            if icc:
                save_kwargs["icc_profile"] = icc

            ext = src_path.suffix.lower()
            if ext in {".jpg", ".jpeg"}:
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
                if cropped_img.mode in ("RGBA", "P"):
                    cropped_img = cropped_img.convert("RGB")
            elif ext == ".webp":
                save_kwargs["quality"] = quality
            elif ext == ".png":
                save_kwargs["optimize"] = True

            cropped_img.save(out_path, **save_kwargs)

            if has_crop:
                return True, f"已裁切 [{orig_w}x{orig_h} -> {new_w}x{new_h}] (切除 T:{top}, B:{orig_h-bottom}, L:{left}, R:{orig_w-right}) -> {out_path.name}"
            else:
                return True, f"無白邊未裁切 [{orig_w}x{orig_h}] -> {out_path.name}"

    except Exception as e:
        return False, f"處理失敗: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="批次去除圖片白邊工具 - 自動偵測並裁切圖片四邊白色背景"
    )
    parser.add_argument(
        "-d", "-f", "--dir", "--folder",
        dest="folder",
        type=str,
        default=None,
        help="指定圖片所在資料夾 (若未指定則彈窗選擇)",
    )
    parser.add_argument(
        "-o", "--out", "--output-subfolder",
        dest="output_subfolder",
        type=str,
        default=DEFAULT_OUTPUT_SUBFOLDER,
        help=f"輸出子資料夾名稱 (預設: {DEFAULT_OUTPUT_SUBFOLDER})",
    )
    parser.add_argument(
        "-t", "-th", "--threshold",
        dest="threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"白邊判定門檻 (0~255，RGB 皆大於等於此值即判定為白色，預設: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "-w", "-wm", "--ignore-watermark",
        dest="ignore_watermark",
        action="store_true",
        help="自動排除底部與主體分離的孤立浮水印文字 (例如 wbg.py 產生的文字邊框)",
    )
    parser.add_argument(
        "-p", "-pd", "--padding",
        dest="padding",
        type=int,
        default=0,
        help="裁切時保留的安全邊距像素 (預設: 0)",
    )
    parser.add_argument(
        "-q", "-ql", "--quality",
        dest="quality",
        type=int,
        default=95,
        help="JPEG/WebP 輸出品質 1-100 (預設: 95)",
    )

    args = parser.parse_args()

    # 選擇資料夾
    if args.folder:
        folder = Path(os.path.expanduser(args.folder))
        if not folder.exists() or not folder.is_dir():
            print(f"錯誤：資料夾不存在：{args.folder}")
            return
    else:
        folder = select_folder()

    if not folder:
        print("未選擇資料夾，程序結束。")
        return

    # 設定輸出子資料夾
    out_dir = folder / args.output_subfolder
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n來源資料夾: {folder}")
    print(f"輸出子資料夾: {out_dir}")
    print(f"白邊門檻值: {args.threshold}")
    print(f"排除底部浮水印: {'是' if args.ignore_watermark else '否'}")
    print(f"保留邊距 (padding): {args.padding} px\n")

    # 收集資料夾中的圖片 (不遞迴搜尋子資料夾)
    image_files = sorted([
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ])

    if not image_files:
        print("指定資料夾中未找到支援的圖片檔案。")
        return

    print(f"共找到 {len(image_files)} 張圖片，開始處理...\n")

    success_count = 0
    fail_count = 0

    for idx, img_path in enumerate(image_files, 1):
        print(f"[{idx}/{len(image_files)}] 正在處理: {img_path.name} ... ", end="", flush=True)
        success, msg = process_image(
            img_path,
            out_dir,
            threshold=args.threshold,
            ignore_watermark=args.ignore_watermark,
            padding=args.padding,
            quality=args.quality,
        )
        if success:
            success_count += 1
            print(f"成功: {msg}")
        else:
            fail_count += 1
            print(f"失敗: {msg}")

    print("\n" + "=" * 50)
    print(f"處理完成！ 成功: {success_count} 張，失敗: {fail_count} 張")
    print(f"輸出檔案存放於: {out_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
