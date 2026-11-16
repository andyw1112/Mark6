# 六合彩生肖沖合

靜態網站：`index.html` 讀取 `draws.txt` 做回測；GitHub Actions 定時更新 `draws.txt`。

## 部署
1. 新增 public repo，上傳本資料夾所有檔案（包括 `.github` 同 `.nojekyll`）。
2. Settings → Pages → Branch 揀 `main` / `(root)` → Save。
3. Actions 分頁 → "Update draws" → Run workflow，手動跑一次，確認成功。
4. 之後逢二、四、六、日 22:00 及 00:00（香港時間）自動更新。

## 手動更新
直接編輯 `draws.txt`，格式：`26/122, 2026-11-17, 3 9 12 25 30 41, 18 | 備註`
