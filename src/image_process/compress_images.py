#!/usr/bin/env python3
"""
批次壓縮圖片至 SNS 用尺寸
目標：每張 1-2MB，適合 Instagram、Twitter、Facebook 等
執行時會跳出資料夾選擇視窗
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image

# SNS 常用最大邊長（多數平台 1080~1920）
MAX_DIMENSION = 1920
# 目標檔案大小（bytes）
TARGET_SIZE_MIN = 1 * 1024 * 1024   # 1 MB
TARGET_SIZE_MAX = 2 * 1024 * 1024   # 2 MB
TARGET_SIZE_OPTIMAL = int(1.5 * 1024 * 1024)  # 1.5 MB
# 輸出子資料夾名稱
OUTPUT_SUBFOLDER = "compressed"
# 支援的圖片格式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def select_folder() -> Path | None:
    """用 macOS AppleScript 跳出原生資料夾選擇視窗（避開 Tkinter 相容性問題）"""
    result = subprocess.run(
        ["osascript", "-e", 'POSIX path of (choose folder with prompt "選擇要壓縮的圖片資料夾")'],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return None


import argparse

def resize_for_sns(img: Image.Image, max_dimension: int = MAX_DIMENSION) -> Image.Image:
    """將圖片縮小至 SNS 常用尺寸（最長邊 max_dimension）"""
    w, h = img.size
    if max(w, h) <= max_dimension:
        return img
    if w >= h:
        new_w = max_dimension
        new_h = int(h * max_dimension / w)
    else:
        new_h = max_dimension
        new_w = int(w * max_dimension / h)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def compress_to_target_size(img: Image.Image, target_bytes: int) -> bytes:
    """
    用二分管調整 JPEG 品質，使輸出約等於目標大小
    """
    # 先轉 RGB（若是 RGBA 或 P 模式）
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    low, high = 50, 95
    best_result: bytes | None = None
    best_diff = float("inf")

    for _ in range(10):  # 二分管最多 10 次
        q = (low + high) // 2
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True)
        data = buf.getvalue()
        size = len(data)
        diff = abs(size - target_bytes)

        if diff < best_diff:
            best_diff = diff
            best_result = data
        if size < target_bytes:
            low = q + 1
        else:
            high = q - 1
        if low > high:
            break

    if best_result is not None:
        return best_result
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue()


def process_image(src_path: Path, out_dir: Path, max_dimension: int = MAX_DIMENSION, target_bytes: int = TARGET_SIZE_OPTIMAL) -> tuple[bool, str]:
    """
    壓縮單張圖片，存到 out_dir，檔名加 _compressed
    回傳 (成功與否, 訊息)
    """
    try:
        img = Image.open(src_path)
        img.load()
    except Exception as e:
        return False, f"無法開啟: {e}"

    # 縮小至 SNS 尺寸
    img_resized = resize_for_sns(img, max_dimension)
    # 壓縮至目標大小
    data = compress_to_target_size(img_resized, target_bytes)

    # 檔名：原名_compressed.jpg
    stem = src_path.stem
    out_path = out_dir / f"{stem}_compressed.jpg"

    try:
        with open(out_path, "wb") as f:
            f.write(data)
        size_mb = len(data) / (1024 * 1024)
        return True, f"OK ({size_mb:.2f} MB) -> {out_path.name}"
    except Exception as e:
        return False, f"寫入失敗: {e}"


def main():
    parser = argparse.ArgumentParser(description="批次壓縮圖片至 SNS 常用尺寸 (1~2MB)")
    parser.add_argument('-d', '-f', '--dir', '--folder', dest='folder', type=str, default=None, help='指定要壓縮的圖片資料夾 (若未指定則彈窗選擇)')
    parser.add_argument('-m', '-mx', '--max-dimension', dest='max_dimension', type=int, default=MAX_DIMENSION, help=f'最長邊限制像素 (預設 {MAX_DIMENSION})')
    parser.add_argument('-s', '-sz', '--target-size', dest='target_size', type=float, default=1.5, help='目標檔案大小 MB (預設 1.5)')
    parser.add_argument('-o', '--out', dest='output_subfolder', type=str, default=OUTPUT_SUBFOLDER, help=f'輸出子資料夾名稱 (預設 {OUTPUT_SUBFOLDER})')
    args = parser.parse_args()

    if args.folder:
        folder = Path(args.folder)
        if not folder.exists() or not folder.is_dir():
            print(f"錯誤：資料夾不存在：{args.folder}")
            return
    else:
        folder = select_folder()
        
    if not folder:
        print("未選擇資料夾，結束。")
        return

    out_dir = folder / args.output_subfolder
    out_dir.mkdir(exist_ok=True)

    # 收集要處理的圖片
    images = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not images:
        print(f"在 {folder} 下找不到支援的圖片檔。")
        return

    target_bytes = int(args.target_size * 1024 * 1024)
    print(f"找到 {len(images)} 張圖片，開始壓縮到 {out_dir}")
    ok, fail = 0, 0
    for p in images:
        success, msg = process_image(p, out_dir, max_dimension=args.max_dimension, target_bytes=target_bytes)
        if success:
            ok += 1
            print(f"  ✓ {p.name}: {msg}")
        else:
            fail += 1
            print(f"  ✗ {p.name}: {msg}")

    print(f"\n完成：成功 {ok} 張，失敗 {fail} 張。")
    print(f"輸出資料夾：{out_dir}")


if __name__ == "__main__":
    main()
