# photo-kit 攝影與圖片處理工具包

`photo-kit` 是一個集合了多種攝影後製、圖片處理、影片轉換及檔案管理腳本的自動化工具包。透過整合式的互動選單，您可以輕鬆地在 macOS 或 Windows 上執行各式功能，無需記憶複雜的終端機指令。

## 🎯 核心機能

本工具包包含四大類別的機能：

1. **📷 照片白邊與浮水印 (`src/watermark/`)**
   - 包含著名的 `wbg.py` 工具。
   - 自動為照片加上 1:1 的白色邊框。
   - 自動讀取 EXIF 資訊，並於底部加入「相機型號 / 鏡頭資訊」的專業文字標記。
   - 💡 詳細設定與說明請參考：[wbg.py 使用手冊](docs/wbg-manual.md)

2. **🖼️ 圖片處理與排版 (`src/image_process/`)**
   - **批次壓縮圖片 (`compress_images.py`)**：將大量高畫質圖片壓縮至 1~2 MB，適合上傳至 Instagram、Twitter、Facebook 等社群平台。
   - **合併多張照片 (`merge_4_photos.py`)**：快速將四張照片以方陣的形式合併為一張大圖。

3. **🎬 圖片轉影片 (`src/video_gen/`)**
   - **`main.py`**：將連續編號的照片序列，無縫轉換為 MP4 影片（支援自訂 FPS 幀數，透過參數 `--loop` 亦可產生無窮迴圈效果）。

4. **📁 檔案整理與命名 (`src/file_manage/`)**
   - **歸檔工具 (`move.py`)**：根據檔名關鍵字，自動將下載的檔案移動到對應的雲端硬碟或分類資料夾。
   - **重命名工具 (`reCreateTime.py`)**：依據 Twitter、Instagram 的檔名格式特徵進行批次改名處理。

---

## 🚀 快速開始

### 1. 系統需求
- Python 3.6 或更高版本
- 支援 macOS / Windows / Linux

### 2. 環境安裝
強烈建議使用虛擬環境 (Virtual Environment) 來執行以避免干擾系統套件：
```bash
# 建立虛擬環境
python3 -m venv venv

# 啟動虛擬環境 (macOS/Linux)
source venv/bin/activate
# Windows 請使用: venv\Scripts\activate

# 安裝相依套件
pip install -r requirements.txt
```

### 3. 如何執行 (互動式選單)
在根目錄中，我們提供了一個整合啟動器。只要執行對應的啟動檔，就會出現方便的互動選單供您挑選功能：

**macOS / Linux:**
```bash
./run.sh
# 或是
python3 run.py
```

**Windows:**
```cmd
run.bat
```

執行後畫面將顯示如下，只要輸入對應數字按下 Enter 即可啟動功能：
```text
==================================================
 photo-kit 工具整合啟動器
==================================================
[1] 照片加白邊與浮水印 (wbg.py)
[2] 批次壓縮圖片 (compress_images.py)
[3] 合併多張照片 (自動白邊排版) (combine_photos.py)
[4] 圖片轉影片 (支援迴圈) (img2video.py)
[5] 檔案整理工具 (move.py)
[6] 依格式重命名工具 (reCreateTime.py)
[7] 連拍廢片清理 (burst_filter.py)
[8] 匯出 Capture One 資料夾清單 (export_c1_folders.py)
[9] チェキ自動裁切 (cheki_crop.py)
[q] 退出
==================================================
請選擇要執行的機能 (例如: 1): 
```

---

## ⚡ 常用參數簡化縮寫 (最多 2 文字)

各機能均支援極簡的 1~2 字短參數（同時向下相容原本的完整長參數），在終端機或 `run.py` 附加參數輸入時更加敏捷：

| 分類 | 腳本 | 縮寫參數 (1~2字) | 完整參數名稱 | 說明與預設值 |
| :--- | :--- | :--- | :--- | :--- |
| **📷 浮水印** | `wbg.py` | `-t` | `--add-text` | 增加相機/鏡頭 EXIF 文字標記 |
| | | `-p` | `--pick-files` | 用原生檔案視窗多選圖片 |
| | | `-a` / `-ar` | `--aspect` | 成品畫布比例 (auto, square, 1:1, 4:3, 16:9) |
| | | `-b` / `-br` | `--border-ratio` | 白邊佔比 (0~1, 預設 0.16) |
| | | `-e` / `-be` | `--border-equal` | 四邊白邊等寬 (依長邊比例) |
| | | `-H` / `-mh` | `--manual-help` | 顯示詳細使用說明書 |
| | | `-v` | `--version` | 顯示版本資訊 |
| **🖼️ 圖片處理** | `compress_images.py` | `-d` / `-f` | `--dir` / `--folder` | 指定圖片資料夾 (留空則彈窗選擇) |
| | | `-m` / `-mx` | `--max-dimension` | 最長邊限制像素 (預設 1920) |
| | | `-s` / `-sz` | `--target-size` | 目標大小 MB (預設 1.5) |
| | | `-o` | `--out` | 輸出子資料夾名稱 (預設 compressed) |
| | `merge_4_photos.py` | `-n` | `--num` | 要合併的照片數量 (預設 4) |
| | | `-q` / `-ql` | `--quality` | 輸出圖片品質 1-100 (預設 95) |
| **🎬 影片生成** | `main.py` | `-n` / `-d` | `-name` / `--name` | Downloads 下的子資料夾名稱 |
| | | `-f` | `-f` / `--fps` | 每張照片顯示秒數 (預設 0.2 秒) |
| | | `-p` / `-pt` | `--pattern` | 檔名匹配模式 (預設 *.jpg) |
| | | `-l` / `-lp` | `--loop` | 啟用往返迴圈效果 (Boomerang) |
| | `main-jp.py` | `-p` / `-d` | `--path` | 圖片資料夾路徑 |
| | | `-r` | `--fps` | 影片幀率 fps (預設 20) |
| **📁 檔案管理** | `move.py` | `-y` | `--yes` / `--force` | 自動確認執行，不跳出確認詢問 |
| | | `-s` | `--source` | 來源資料夾 (預設 ~/Downloads) |
| | | `-c` | `--config` | 規則設定檔路徑 (預設 file_rules.local.json / file_rules.json) |
| | | `-d` / `-dr` | `--dry-run` | 模擬執行，只列印不實際移動 |
| | `reCreateTime.py` | `-m` / `-mv` | `--move` | 是否移動至子資料夾 (y/n) |
| | | `-d` / `-dir` | `--dir` / `--folder` | 要處理的資料夾路徑 (留空彈窗) |
| | `burst_filter.py` | `-d` / `-dr` | `--dry-run` | 模擬執行，只列印不實際移動 |
| | | `-t` / `-tt` | `--time-threshold` | 連拍判定秒數閾值 (預設 3) |
| | | `-s` / `-ht` | `--hash-threshold` | 視覺差異度閾值 (預設 15) |
| | | `-db` | `--db` | Capture One 資料庫路徑 |
| | `export_c1_folders.py` | `-f` / `-fl` | `--filter` | 啟用日期過濾 |
| | | `-k` / `-kw` | `--keyword` | 自訂過濾關鍵字 (* 為全部匯出) |
| | | `-r` / `-rg` | `--regex` | 過濾正則表達式 |
| | | `-o` | `--out` | 匯出檔案路徑 |
| | | `-db` | `--db` | Capture One 資料庫路徑 |

---

## 📂 資料夾結構說明

為了更良好的擴充性與管理，程式碼已被分類至以下結構：

```text
photo-kit/
├── README.md               # 本專案首頁說明
├── requirements.txt        # 相依套件清單 (Pip)
├── run.py                  # 互動式啟動主程式
├── run.sh / run.bat        # macOS/Windows 捷徑啟動腳本
├── docs/                   # 附加文件存放區
│   └── wbg-manual.md       # (wbg.py 詳細說明書)
└── src/                    # 原始程式碼目錄
    ├── watermark/          # 白邊與浮水印腳本
    ├── image_process/      # 壓縮與合併腳本
    ├── video_gen/          # 影片生成腳本
    └── file_manage/        # 檔案管理腳本
```

---

*Enjoy your automated photo and video workflows!*
