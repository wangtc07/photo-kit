import os
import sys
import argparse
from typing import Optional, Tuple, List
import numpy as np
import cv2
from AppKit import NSOpenPanel, NSApplication
from web_ui import start_web_review

# =====================================================================
# チェキ（Instax）自動裁切ツール v3
#
# 検出戦略（優先順）:
#   1. Hough 直線検出 + 4 辺矩形組み立て（最高精度）
#      白い外枠の 4 辺をそれぞれ独立に検出→交点を角として使用
#   2. Apple Vision VNDetectRectanglesRequest（ML ベース）
#   3. OpenCV 白色外枠 HSV 検出
#
# 出力サイズ: 86mm × 54mm 比率（長辺 4K = 3840px、短辺 ≈ 2411px）
# =====================================================================

CHEKI_LONG_PX  = 3840
CHEKI_SHORT_PX = round(3840 * 54 / 86)   # ≈ 2411 px
OUTPUT_W = CHEKI_SHORT_PX   # 2411
OUTPUT_H = CHEKI_LONG_PX    # 3840
CHEKI_RATIO = 86 / 54       # ≈ 1.593
RATIO_MIN = 1.20
RATIO_MAX = 1.90


# =====================================================================
# ユーティリティ
# =====================================================================

def ask_open_directory(title: str = "選擇資料夾") -> Optional[str]:
    app = NSApplication.sharedApplication()
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setCanChooseFiles_(False)
    panel.setCanChooseDirectories_(True)
    panel.setAllowsMultipleSelection_(False)
    if panel.runModal() == 1:
        urls = panel.URLs()
        if urls:
            return str(urls[0].path())
    return None


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    4 点を [左上, 右上, 右下, 左下] に整列。
    外積で巻き方向を確認し時計回りなら TL/TR を入れ替え。
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    # 巻き方向チェック
    v1 = rect[1] - rect[0]
    v2 = rect[2] - rect[1]
    if v1[0] * v2[1] - v1[1] * v2[0] < 0:
        rect[1], rect[3] = rect[3].copy(), rect[1].copy()
    return rect


def quad_ratio(pts: np.ndarray) -> float:
    rect = order_points(pts)
    w = np.linalg.norm(rect[1] - rect[0])
    h = np.linalg.norm(rect[3] - rect[0])
    return max(w, h) / max(min(w, h), 1)


def is_cheki_ratio(pts: np.ndarray) -> bool:
    return RATIO_MIN <= quad_ratio(pts) <= RATIO_MAX


def line_intersection(l1: np.ndarray, l2: np.ndarray) -> Optional[np.ndarray]:
    """2 直線（各 [rho, theta]）の交点を返す。平行なら None。"""
    rho1, theta1 = l1
    rho2, theta2 = l2
    A = np.array([
        [np.cos(theta1), np.sin(theta1)],
        [np.cos(theta2), np.sin(theta2)],
    ])
    b = np.array([rho1, rho2])
    det = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
    if abs(det) < 1e-6:
        return None
    x = (A[1, 1] * b[0] - A[0, 1] * b[1]) / det
    y = (-A[1, 0] * b[0] + A[0, 0] * b[1]) / det
    return np.array([x, y], dtype=np.float32)


# =====================================================================
# 検出方法 1: Hough 直線 + 4 辺組み立て（主力）
# =====================================================================

def get_hough_lines(mask: np.ndarray, scale: int, threshold: int = 80) -> List[np.ndarray]:
    blurred = cv2.GaussianBlur(mask, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)
    small = cv2.resize(edges, (mask.shape[1] // scale, mask.shape[0] // scale))
    lines = cv2.HoughLines(small, 1, np.pi / 180, threshold=threshold)
    if lines is None:
        return []
    lines = lines[:, 0, :]
    lines[:, 0] *= scale
    return lines.tolist()

def find_cheki_quad_hough(img_bgr: np.ndarray,
                           img_w: int, img_h: int) -> Optional[np.ndarray]:
    """
    Dual Mask Hough 直線検出 + 4 辺矩形組み立て（最高精度）
    - mask_white: HSV で純白を抽出（キーボード排除用。下辺が正確）
    - mask_bright: グレースケールで暗い背景以外を抽出（マーカーの描画を含む。上左右が正確）
    両方のエッジを合わせて全直線を組み合わせ、最も物理チェキ比率 (1.59) に近いものを探す。
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    best_corners = None
    best_score = -float('inf')

    # 1. Mask White (HSV) - 純粋な白い枠（下辺のキーボード分離に強い）
    best_mask_white = None
    max_area_white = 0
    for s_max, v_min in [(50, 170), (70, 150), (40, 185), (100, 130)]:
        m = cv2.inRange(hsv, np.array([0, 0, v_min]), np.array([180, s_max, 255]))
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k, iterations=1)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in cnts if 0.04 * img_w * img_h <= cv2.contourArea(c) <= 0.60 * img_w * img_h]
        if valid:
            best_c = max(valid, key=cv2.contourArea)
            area = cv2.contourArea(best_c)
            if area > max_area_white:
                max_area_white = area
                best_mask_white = np.zeros_like(m)
                cv2.drawContours(best_mask_white, [best_c], -1, 255, -1)
                
    # 2. Mask Bright (Gray > 60) - 暗い背景以外（マーカー塗りのエッジに強い）
    blur_gray = cv2.GaussianBlur(gray, (9, 9), 0)
    _, thresh = cv2.threshold(blur_gray, 60, 255, cv2.THRESH_BINARY)
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask_bright_raw = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k2, iterations=3)
    mask_bright_raw = cv2.morphologyEx(mask_bright_raw, cv2.MORPH_OPEN, k2, iterations=1)
    cnts, _ = cv2.findContours(mask_bright_raw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_mask_bright = None
    if cnts:
        best_c = max(cnts, key=cv2.contourArea)
        # 広すぎる（背景全体）場合は除外
        if cv2.contourArea(best_c) <= 0.80 * img_w * img_h:
            best_mask_bright = np.zeros_like(mask_bright_raw)
            cv2.drawContours(best_mask_bright, [best_c], -1, 255, -1)
        
    lines_all = []
    if best_mask_white is not None:
        lines_all.extend(get_hough_lines(best_mask_white, 4, threshold=80))
    if best_mask_bright is not None:
        lines_all.extend(get_hough_lines(best_mask_bright, 4, threshold=80))
        
    if not lines_all:
        return None
        
    H_THRESH = np.radians(25)
    V_THRESH = np.radians(25)
    horiz = []
    vert = []
    
    for rho, theta in lines_all:
        if theta > np.pi:
            theta -= np.pi
            rho = -rho
        if theta < H_THRESH or theta > np.pi - H_THRESH:
            vert.append([rho, theta])
        elif abs(theta - np.pi / 2) < V_THRESH:
            horiz.append([rho, theta])

    if len(horiz) < 2 or len(vert) < 2:
        return None

    horiz = sorted(horiz, key=lambda x: x[0])
    vert = sorted(vert, key=lambda x: x[0])

    def deduplicate_lines(lines_list, dist_thresh):
        res = []
        for l in lines_list:
            if not res:
                res.append(l)
            elif abs(l[0] - res[-1][0]) > dist_thresh:
                res.append(l)
        return res

    horiz = deduplicate_lines(horiz, 40)
    vert = deduplicate_lines(vert, 40)

    import itertools
    for top, bot in itertools.combinations(horiz, 2):
        for left, right in itertools.combinations(vert, 2):
            tl = line_intersection(top, left)
            tr = line_intersection(top, right)
            br = line_intersection(bot, right)
            bl = line_intersection(bot, left)
            if any(p is None for p in [tl, tr, br, bl]):
                continue

            corners = np.array([tl, tr, br, bl], dtype=np.float32)

            margin = 0.15
            if not all(-margin * img_w <= p[0] <= img_w * (1 + margin) and 
                       -margin * img_h <= p[1] <= img_h * (1 + margin) for p in corners):
                continue

            area = cv2.contourArea(order_points(corners).reshape(-1, 1, 2))
            if not (0.04 * img_w * img_h <= area <= 0.60 * img_w * img_h):
                continue

            ratio = quad_ratio(corners)
            if 1.45 <= ratio <= 1.75:
                # 面積を最大化しつつ、比率のズレを軽くペナルティとして扱う
                score = area / (1.0 + 5 * abs(ratio - CHEKI_RATIO))
                if score > best_score:
                    best_score = score
                    best_corners = corners

    return best_corners


# =====================================================================
# 検出方法 2: Apple Vision ML
# =====================================================================

def find_cheki_quad_vision(img_bgr: np.ndarray,
                            img_w: int, img_h: int) -> Optional[np.ndarray]:
    """
    Apple Vision で全候補を取得し、
    「チェキ比率内 (1.20~1.90) かつ面積最大」のものを返す。
    """
    try:
        import Vision
        import Quartz
    except ImportError:
        return None

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    data = img_rgb.tobytes()
    provider = Quartz.CGDataProviderCreateWithData(None, data, len(data), None)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    cg = Quartz.CGImageCreate(
        img_w, img_h, 8, 24, img_w * 3, cs,
        Quartz.kCGBitmapByteOrderDefault | Quartz.kCGImageAlphaNone,
        provider, None, False, Quartz.kCGRenderingIntentDefault
    )
    if cg is None:
        return None

    req = Vision.VNDetectRectanglesRequest.alloc().init()
    req.setMinimumAspectRatio_(0.10)
    req.setMaximumAspectRatio_(0.99)
    req.setMinimumSize_(0.01)
    req.setMaximumObservations_(20)
    req.setMinimumConfidence_(0.1)
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg, {}
    ).performRequests_error_([req], None)

    candidates = []
    for obs in (req.results() or []):
        tl = obs.topLeft(); tr = obs.topRight()
        br = obs.bottomRight(); bl = obs.bottomLeft()
        pts = np.array([
            [tl.x * img_w, (1 - tl.y) * img_h],
            [tr.x * img_w, (1 - tr.y) * img_h],
            [br.x * img_w, (1 - br.y) * img_h],
            [bl.x * img_w, (1 - bl.y) * img_h],
        ], dtype=np.float32)
        area = cv2.contourArea(pts.reshape(-1, 1, 2))
        if area < 0.03 * img_w * img_h:
            continue
        if is_cheki_ratio(pts):
            candidates.append((pts, area))

    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])[0]


# =====================================================================
# 検出方法 3: HSV 白色輪郭
# =====================================================================

def find_cheki_quad_by_white(img_bgr: np.ndarray,
                              img_w: int, img_h: int) -> Optional[np.ndarray]:
    """チェキの白いボーダーを HSV で抽出し 4 角形に近似する。"""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    best_pts = None
    best_area = 0

    for s_max, v_min in [(40, 185), (55, 170), (70, 155), (90, 140)]:
        mask = cv2.inRange(hsv,
                           np.array([0, 0, v_min]),
                           np.array([180, s_max, 255]))
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
                                iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            area = cv2.contourArea(cnt)
            if not (0.04 * img_w * img_h <= area <= 0.60 * img_w * img_h):
                continue
            peri = cv2.arcLength(cnt, True)
            for eps in [0.01, 0.02, 0.03, 0.04, 0.05]:
                approx = cv2.approxPolyDP(cnt, eps * peri, True)
                if len(approx) == 4:
                    pts = approx.reshape(4, 2).astype(np.float32)
                    if is_cheki_ratio(pts) and area > best_area:
                        best_pts = pts
                        best_area = area
                    break

    return best_pts if best_area > 0.04 * img_w * img_h else None


# =====================================================================
# メイン検出（全手法 fallback）
# =====================================================================

def detect_cheki_quad(img_bgr: np.ndarray) -> Tuple[Optional[np.ndarray], str]:
    img_h, img_w = img_bgr.shape[:2]

    pts = find_cheki_quad_hough(img_bgr, img_w, img_h)
    if pts is not None:
        return pts, "hough"

    pts = find_cheki_quad_vision(img_bgr, img_w, img_h)
    if pts is not None:
        return pts, "vision"

    pts = find_cheki_quad_by_white(img_bgr, img_w, img_h)
    if pts is not None:
        return pts, "white"

    return None, "failed"


# =====================================================================
# 透視変換・クロップ
# =====================================================================

def warp_cheki(img_bgr: np.ndarray, src_pts: np.ndarray) -> np.ndarray:
    """透視変換でチェキを正面化・クロップ（縦向き固定）"""
    rect = order_points(src_pts)
    w_top = np.linalg.norm(rect[1] - rect[0])
    h_left = np.linalg.norm(rect[3] - rect[0])
    if w_top > h_left:
        rect = np.array([rect[3], rect[0], rect[1], rect[2]], dtype=np.float32)
    pad_w = OUTPUT_W * (1.0 / 54.0)
    pad_h = OUTPUT_H * (1.0 / 86.0)
    dst = np.array([
        [pad_w,               pad_h],
        [OUTPUT_W - 1 - pad_w, pad_h],
        [OUTPUT_W - 1 - pad_w, OUTPUT_H - 1 - pad_h],
        [pad_w,               OUTPUT_H - 1 - pad_h],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img_bgr, M, (OUTPUT_W, OUTPUT_H),
                               flags=cv2.INTER_LANCZOS4)


def save_debug_image(img_bgr: np.ndarray, pts: np.ndarray, output_path: str):
    h, w = img_bgr.shape[:2]
    scale = min(1.0, 1500 / max(w, h))
    debug = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))
    pts_s = (pts * scale).astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(debug, [pts_s], True, (0, 0, 255), 5)
    for i, pt in enumerate(order_points(pts) * scale):
        cv2.circle(debug, tuple(pt.astype(int)), 15, (0, 255, 0), -1)
        cv2.putText(debug, str(i), tuple(pt.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    cv2.imwrite(output_path, debug)

def save_training_data(img: np.ndarray, pts: np.ndarray, fname: str, method: str, annotation_file: str, base_dir: str):
    try:
        import json, time
        images_dir = os.path.join(base_dir, "data", "images")
        os.makedirs(images_dir, exist_ok=True)
        
        # Scale down to max 800px
        h, w = img.shape[:2]
        train_scale = min(1.0, 800.0 / max(w, h))
        img_train = cv2.resize(img, (int(w * train_scale), int(h * train_scale)), interpolation=cv2.INTER_AREA)
        pts_train = pts * train_scale
        
        # Use timestamp to prevent overwrite if processing different folders with same filename
        unique_prefix = str(int(time.time()))[-6:]
        train_img_name = f"{unique_prefix}_{fname}"
        train_img_path = os.path.join(images_dir, train_img_name)
        
        # Save compressed JPEG
        cv2.imwrite(train_img_path, img_train, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        with open(annotation_file, 'a', encoding='utf-8') as f:
            record = {
                "filename": train_img_name,
                "original_filename": fname,
                "method": method,
                "points": pts_train.tolist(),
                "width": img_train.shape[1],
                "height": img_train.shape[0]
            }
            f.write(json.dumps(record) + '\n')
    except Exception:
        pass


# =====================================================================
# バッチ処理
# =====================================================================

def process_folder(folder: str, output_subdir: str,
                   extensions: List[str], debug: bool, review: bool
                   ) -> Tuple[int, int, List[str]]:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    annotation_file = os.path.join(base_dir, "data", "cheki_annotations.jsonl")
    os.makedirs(os.path.dirname(annotation_file), exist_ok=True)
    
    all_files = []
    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lstrip('.')
        if ext.lower() in extensions:
            all_files.append(os.path.join(folder, fname))

    if not all_files:
        print(f"[警告] 対象ファイルが見つかりませんでした: {folder}")
        return 0, 0, []

    out_dir = os.path.join(folder, output_subdir)
    os.makedirs(out_dir, exist_ok=True)
    if debug:
        debug_dir = os.path.join(folder, output_subdir + "_debug")
        os.makedirs(debug_dir, exist_ok=True)

    success_count = 0
    fail_count = 0
    failed_files: List[str] = []

    if review:
        print("\n[第一階段] 背景自動掃描圖片...")
        review_data = []
        for i, fpath in enumerate(all_files, 1):
            fname = os.path.basename(fpath)
            print(f"  ({i}/{len(all_files)}) 分析 {fname} ...", end="\r")
            img = cv2.imread(fpath, cv2.IMREAD_COLOR)
            if img is None:
                fail_count += 1; failed_files.append(fname)
                continue
            
            pts, method = detect_cheki_quad(img)
            if pts is None:
                h, w = img.shape[:2]
                pad = min(w, h) * 0.1
                pts = np.array([
                    [pad, pad], [w-pad, pad], [w-pad, h-pad], [pad, h-pad]
                ], dtype=np.float32)
                method = "ManualFallback"
                
            review_data.append({
                "filename": fname,
                "path": fpath,
                "points": pts.tolist(),
                "method": method
            })
            
        if not review_data:
            return 0, fail_count, failed_files
            
        final_data = start_web_review(review_data)
        
        print("\n[第二階段] 開始批次裁切與儲存...")
        for i, item in enumerate(final_data, 1):
            fname = item['filename']
            fpath = item['path']
            pts = np.array(item['points'], dtype=np.float32)
            method = item['method']
            
            print(f"[{i}/{len(final_data)}] {fname}", end="  ", flush=True)
            img = cv2.imread(fpath, cv2.IMREAD_COLOR)
            if img is None:
                print("→ [失敗] 讀取錯誤")
                continue
                
            print(f"→ [{method}]", end="  ", flush=True)
            if debug:
                save_debug_image(img, pts, os.path.join(debug_dir, fname))

            warped = warp_cheki(img, pts)
            stem = os.path.splitext(fname)[0]
            out_path = os.path.join(out_dir, stem + ".jpg")
            cv2.imwrite(out_path, warped, [cv2.IMWRITE_JPEG_QUALITY, 98])
            
            # Save annotation and compressed image for training
            save_training_data(img, pts, fname, method, annotation_file, base_dir)
                
            print(f"→ {os.path.basename(out_path)}")
            success_count += 1
            
        return success_count, fail_count, failed_files
        
    # 非 Web UI 審查模式（原有的單張串流處理）
    for i, fpath in enumerate(all_files, 1):
        fname = os.path.basename(fpath)
        print(f"[{i}/{len(all_files)}] {fname}", end="  ", flush=True)

        img = cv2.imread(fpath, cv2.IMREAD_COLOR)
        if img is None:
            print("→ [失敗] 読み込みエラー")
            fail_count += 1; failed_files.append(fname); continue

        pts, method = detect_cheki_quad(img)
        if pts is None:
            print("→ [失敗] 検出不可")
            fail_count += 1; failed_files.append(fname); continue

        print(f"→ [{method}]", end="  ", flush=True)
        if debug:
            save_debug_image(img, pts, os.path.join(debug_dir, fname))

        warped = warp_cheki(img, pts)
        stem = os.path.splitext(fname)[0]
        out_path = os.path.join(out_dir, stem + ".jpg")
        cv2.imwrite(out_path, warped, [cv2.IMWRITE_JPEG_QUALITY, 98])
        
        # Save annotation and compressed image for training
        save_training_data(img, pts, fname, method, annotation_file, base_dir)
            
        print(f"→ {os.path.basename(out_path)}")
        success_count += 1

    return success_count, fail_count, failed_files


# =====================================================================
# エントリポイント
# =====================================================================

parser = argparse.ArgumentParser(
    description="チェキ（Instax）翻拍写真を自動検出・透視補正・クロップする"
)
parser.add_argument('-d', '--dir', dest='directory', type=str, default=None,
                    help='処理する資料夾（省略時はダイアログ）')
parser.add_argument('-o', '--output', dest='output', type=str,
                    default='cheki_crop', help='出力サブフォルダ名')
parser.add_argument('-e', '--ext', dest='ext', type=str,
                    default='jpg,jpeg,png,tif,tiff',
                    help='対象拡張子（カンマ区切り）')
parser.add_argument('--debug', dest='debug', action='store_true', default=False,
                    help='デバッグ画像を出力する')
parser.add_argument('-r', '--review', dest='review', action='store_true', default=False,
                    help='手動で4隅を微調整するUIを表示する')
args = parser.parse_args()

folder = args.directory
if folder is None:
    folder = ask_open_directory("選擇要處理的資料夾（チェキ翻拍写真フォルダ）")
    if folder is None:
        print("キャンセルされました。"); sys.exit(0)

if not os.path.isdir(folder):
    print(f"[エラー] {folder}"); sys.exit(1)

extensions = list(set(e.strip().lower().lstrip('.') for e in args.ext.split(',')))

print("=" * 60)
print(" チェキ自動裁切ツール v3")
print("=" * 60)
print(f" 処理資料夾    : {folder}")
print(f" 出力サイズ    : {OUTPUT_W} × {OUTPUT_H} px")
try:
    import Vision
    print(" 検出エンジン  : Hough直線 + Apple Vision ML + HSV白色検出")
except ImportError:
    print(" 検出エンジン  : Hough直線 + HSV白色検出")
print("=" * 60)

success, fail, failed_list = process_folder(
    folder, args.output, extensions, args.debug, args.review
)
print()
print("=" * 60)
print(f" 完了！  成功: {success} / 失敗: {fail}")
if failed_list:
    for f in failed_list:
        print(f"   - {f}")
print(f" 出力先: {os.path.join(folder, args.output)}")
print("=" * 60)
