import requests
import json
import subprocess
import time

# 1. 更新 config.json 中的 grid_number
config_file_path = 'config.json'

def update_config(new_grid_number):
    with open(config_file_path, 'r') as config_file:
        config_data = json.load(config_file)

    config_data['grid_number'] = new_grid_number

    with open(config_file_path, 'w') as config_file:
        json.dump(config_data, config_file, indent=4)

    print(f"已更新 grid_number 為: {new_grid_number}")

# 2. 執行 git push 推送到 GitHub
def git_push():
    try:
        # 添加修改的文件
        subprocess.run(["git", "add", config_file_path], check=True)

        # 提交變更
        subprocess.run(["git", "commit", "-m", f"更新圖號數據: {config_file_path}"], check=True)

        # 推送到 GitHub
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("已成功推送到 GitHub")
    except subprocess.CalledProcessError as e:
        print(f"Git 推送失敗: {e}")

# 3. 從 Cloud Run 下載文件
def download_from_cloud_run():
    # Cloud Run 應用的下載 URL
    download_url = 'https://cloudrun-998441420547.us-central1.run.app/download_data'

    try:
        # 發送 GET 請求下載文件
        response = requests.get(download_url)

        # 檢查請求是否成功
        if response.status_code == 200:
            # 本地保存文件的名稱
            local_filename = 'downloaded_file.zip'
            with open(local_filename, 'wb') as f:
                f.write(response.content)
            print(f"文件已成功下載並保存為: {local_filename}")
        else:
            print(f"文件下載失敗，狀態碼: {response.status_code}")
    except Exception as e:
        print(f"下載失敗: {e}")

# 4. 主程序邏輯
if __name__ == "__main__":
    # 讀取用戶輸入的圖號或縣市代碼
    new_grid_number = input("請輸入圖號或縣市代碼 (例如: 94181SE,9420,10018): ")
    
    # 更新 config.json
    update_config(new_grid_number)

    # 推送到 GitHub
    git_push()

    # 延遲幾秒鐘以確保 Cloud Run 已經更新
    time.sleep(10)  # 根據實際情況調整等待時間

    # 下載文件到本地
    download_from_cloud_run()
