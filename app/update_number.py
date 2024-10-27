import json
import os
import requests  # 新增這一行

# 從命令行輸入獲取號碼
user_input = input("請輸入圖號或縣市代碼 (例如: 94181SE,9420,10018): ")

# 將輸入寫入 config.json 文件
config_data = {
    "grid_number": user_input
}

with open('config.json', 'w') as config_file:
    json.dump(config_data, config_file)

# 自動執行 git 操作
os.system("git add config.json")
os.system(f'git commit -m "更新圖號數據: {user_input}"')
os.system("git push origin main")

# 發送請求到 Cloud Run 來觸發下載
cloud_run_url = 'https://cloudrun-998441420547.us-central1.run.app/download_data'

try:
    # 發送請求以觸發下載
    response = requests.get(cloud_run_url, allow_redirects=True)
    if response.status_code == 200:
        # 檢查是否有重定向到下載 URL
        download_url = response.url  # 這裡取得最終的下載 URL
        print(f"下載 URL: {download_url}")

        # 開始下載文件
        download_response = requests.get(download_url, stream=True)
        if download_response.status_code == 200:
            # 將下載的文件保存到本地
            with open('downloaded_files.zip', 'wb') as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("下載完成，文件已保存為 downloaded_files.zip")
        else:
            print(f"下載失敗，狀態碼: {download_response.status_code}")
    else:
        print(f"觸發失敗，狀態碼: {response.status_code}")
except Exception as e:
    print(f"發送請求時出現錯誤: {e}")
