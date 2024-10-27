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
os.system("git push origin master")

# 發送請求到 Cloud Run 來觸發下載
cloud_run_url = 'https://cloudrun-998441420547.us-central1.run.app/download_data'

try:
    response = requests.get(cloud_run_url)
    if response.status_code == 200:
        print("下載成功觸發！")
    else:
        print(f"觸發失敗，狀態碼: {response.status_code}")
except Exception as e:
    print(f"發送請求時出現錯誤: {e}")
