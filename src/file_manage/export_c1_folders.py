#!/usr/bin/env python3
import sqlite3
import os
import argparse
import re
import sys

def get_c1_folders(db_path, filter_regex=None):
    if not os.path.exists(db_path):
        print(f"錯誤: 找不到 Capture One 資料庫: {db_path}")
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
        SELECT DISTINCT p.ZMACROOT, p.ZRELATIVEPATH 
        FROM ZPATHLOCATION p
        JOIN ZIMAGE i ON i.ZIMAGELOCATION = p.Z_PK
        WHERE p.ZRELATIVEPATH IS NOT NULL
        ORDER BY p.ZMACROOT, p.ZRELATIVEPATH
        """
        cursor.execute(query)

        paths = []
        for r in cursor.fetchall():
            macroot = r["ZMACROOT"] or "/"
            relpath = r["ZRELATIVEPATH"] or ""
            
            if relpath.startswith("/"):
                relpath = relpath[1:]
                
            full_path = os.path.join(macroot, relpath)
            
            if filter_regex:
                # 檢查最後一個資料夾名稱或整個路徑是否包含指定的正規表達式
                if not re.search(filter_regex, full_path):
                    continue
                    
            paths.append(full_path)
            
        return paths
    except Exception as e:
        print(f"資料庫讀取發生錯誤: {e}")
        return []

def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    default_out = os.path.join(project_root, "CaptureOne_Folders.txt")

    parser = argparse.ArgumentParser(description="匯出 Capture One 中有照片的資料夾路徑。")
    parser.add_argument("-db", "--db", dest="db", default=os.path.expanduser("~/Pictures/Capture One Catalog.cocatalog/Capture One Catalog.cocatalogdb"), help="Capture One 資料庫路徑")
    parser.add_argument("-o", "-out", "--out", dest="out", default=default_out, help="匯出檔案路徑 (預設為專案根目錄)")
    parser.add_argument("-f", "-fl", "--filter", dest="filter", action="store_true", help="啟用日期過濾")
    parser.add_argument("-k", "-kw", "--keyword", dest="keyword", default=None, help="自訂過濾關鍵字 (輸入 * 為不限制全部匯出)")
    parser.add_argument("-r", "-rg", "--regex", dest="regex", default=r'(\d{6}|\d{8}|\d{4}-\d{2}-\d{2})', help="過濾正則表達式，預設為日期格式 (YYMMDD, YYYYMMDD, YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    if args.keyword is not None:
        if args.keyword == '*':
            filter_pattern = None
        elif args.keyword == '':
            filter_pattern = args.regex
        else:
            filter_pattern = rf"(?=.*{args.regex})(?=.*{re.escape(args.keyword)})"
    elif len(sys.argv) == 1:
        ans = input("請輸入過濾關鍵字 (留白=預設只保留日期資料夾, 輸入 *=不限制全部匯出): ").strip()
        if ans == '*':
            filter_pattern = None
        elif ans == '':
            filter_pattern = args.regex
        else:
            # 同時包含「自訂關鍵字」與「日期格式」
            filter_pattern = rf"(?=.*{args.regex})(?=.*{re.escape(ans)})"
    else:
        filter_pattern = args.regex if args.filter else None

    print(f"正在從 Capture One 讀取資料...")
    paths = get_c1_folders(args.db, filter_pattern)
    
    if not paths:
        print("沒有找到符合條件的資料夾路徑。")
        return
        
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            for p in paths:
                f.write(p + "\n")
        print(f"✅ 成功匯出 {len(paths)} 個資料夾路徑至: {args.out}")
    except Exception as e:
        print(f"寫入檔案時發生錯誤: {e}")

if __name__ == "__main__":
    main()
