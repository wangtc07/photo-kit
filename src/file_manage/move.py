import os
import shutil
import argparse
import json
from pathlib import Path

def load_rules(config_file=None):
    """
    載入檔案移動對應規則。
    優先順序：
    1. CLI 指定的 config 檔案
    2. 當前目錄或專案根目錄的 file_rules.local.json
    3. 當前目錄或專案根目錄的 file_rules.json
    4. 腳本所在目錄的 file_rules.local.json / file_rules.json
    """
    candidates = []
    if config_file:
        candidates.append(Path(config_file))
    else:
        candidates.extend([
            Path("file_rules.local.json"),
            Path("file_rules.json"),
            Path(__file__).resolve().parent.parent.parent / "file_rules.local.json",
            Path(__file__).resolve().parent.parent.parent / "file_rules.json",
            Path(__file__).resolve().parent / "file_rules.local.json",
            Path(__file__).resolve().parent / "file_rules.json",
        ])

    first_existing = None
    for p in candidates:
        if p.exists() and p.is_file():
            if first_existing is None:
                first_existing = p
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                if rules:
                    return rules, p
            except Exception as e:
                print(f"⚠️ 讀取設定檔 {p} 失敗: {e}")

    return {}, first_existing

def organize_files(source_path=None, dry_run=False, config_path=None):
    if source_path is None:
        source_path = str(Path.home() / "Downloads")

    # 來源資料夾
    source_dir = Path(source_path)

    # 載入檔名對應規則
    file_rules, loaded_config = load_rules(config_path)
    if not file_rules:
        print("⚠️ 未載入任何檔名對應規則。")
        print("請在專案根目錄建立 `file_rules.local.json` 或 `file_rules.json` 並設定對應規則。")
        print('格式範例：\n{\n    "關鍵字": "/目標/資料夾/路徑"\n}')
        if loaded_config:
            print(f"目前讀取的設定檔為空：{loaded_config}")
        return

    
    # 檢查來源資料夾是否存在
    if not source_dir.exists():
        print(f"錯誤：來源資料夾 {source_dir} 不存在")
        return
    
    moved_count = 0
    error_count = 0
    
    print("開始處理檔案...")
    print(f"來源資料夾：{source_dir}")
    print("-" * 50)
    
    # 遍歷Downloads資料夾中的所有檔案
    for file_path in source_dir.iterdir():
        if file_path.is_file():
            filename = file_path.name
            
            # 檢查檔名是否包含任何規則中的關鍵字
            for keyword, dest_folder in file_rules.items():
                if keyword in filename:
                    try:
                        # 確保目標資料夾存在
                        dest_path = Path(dest_folder)
                        if not dry_run:
                            dest_path.mkdir(parents=True, exist_ok=True)
                        
                        # 移動檔案
                        dest_file = dest_path / filename
                        
                        # 如果目標檔案已存在，添加編號
                        counter = 1
                        original_dest_file = dest_file
                        while dest_file.exists():
                            name_parts = original_dest_file.stem, counter, original_dest_file.suffix
                            dest_file = dest_path / f"{name_parts[0]}_{name_parts[1]}{name_parts[2]}"
                            counter += 1
                        
                        if not dry_run:
                            shutil.move(str(file_path), str(dest_file))
                        tag = "模擬移動" if dry_run else "已移動"
                        print(f"✅ {tag}：{filename}")
                        print(f"   → {dest_folder}")
                        print()
                        moved_count += 1
                        break  # 找到匹配規則後跳出迴圈
                        
                    except Exception as e:
                        print(f"❌ 移動檔案失敗：{filename}")
                        print(f"   錯誤：{str(e)}")
                        print()
                        error_count += 1
                        break
    
    # 顯示結果統計
    print("-" * 50)
    print("處理完成！")
    action_str = "模擬移動" if dry_run else "成功移動"
    print(f"{action_str}：{moved_count} 個檔案")
    if error_count > 0:
        print(f"失敗：{error_count} 個檔案")
    
    # 顯示未處理的檔案
    remaining_files = [f.name for f in source_dir.iterdir() if f.is_file()]
    if remaining_files:
        print(f"\n未處理的檔案（{len(remaining_files)} 個）：")
        for file in remaining_files[:10]:  # 只顯示前10個
            print(f"  • {file}")
        if len(remaining_files) > 10:
            print(f"  ... 還有 {len(remaining_files) - 10} 個檔案")

if __name__ == "__main__":
    default_source = str(Path.home() / "Downloads")
    parser = argparse.ArgumentParser(description="根據檔名規則自動分類整理檔案")
    parser.add_argument('-y', '-f', '--yes', '--force', dest='yes', action='store_true', help='自動確認執行，不跳出確認詢問')
    parser.add_argument('-s', '-src', '--source', dest='source', default=default_source, help='來源資料夾 (預設 ~/Downloads)')
    parser.add_argument('-c', '--config', dest='config', default=None, help='規則設定檔路徑 (預設依序搜尋 file_rules.local.json, file_rules.json)')
    parser.add_argument('-d', '-dr', '--dry-run', dest='dry_run', action='store_true', help='模擬執行，只列印不實際移動檔案')
    args = parser.parse_args()

    if not args.yes and not args.dry_run:
        # 安全提示
        print("⚠️  注意：此腳本將會移動檔案，請確認規則正確後再執行")
        print("建議先備份重要檔案")
        
        response = input("\n是否要繼續執行？(y/N): ")
        if response.lower() != 'y':
            print("已取消執行")
            exit(0)

    organize_files(source_path=args.source, dry_run=args.dry_run, config_path=args.config)