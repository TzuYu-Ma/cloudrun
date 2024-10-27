import json
import os

# 從命令行輸入獲取號碼
user_input = input("請輸入圖號或縣市代碼: ")

# 將輸入寫入 config.json 文件
config_data = {
    "grid_number": user_input
}

with open('config.json', 'w') as config_file:
    json.dump(config_data, config_file)

# 自動執行 git 操作
os.system("git add config.json")
os.system('git commit -m "更新圖號數據: {}"'.format(user_input))
os.system("git push")
