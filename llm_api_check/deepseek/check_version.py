import csv
from openai import OpenAI

# 基础配置
API_KEY = "xxxxxxxxxxxxxxxx"
BASE_URL = "https://api.deepseek.com" # DeepSeek 的 API 地址

TXT_FILENAME = "deepseek_models_raw_data.txt"
CSV_FILENAME = "deepseek_models_overview.csv"

# CSV 表头 - DeepSeek (基于 OpenAI 接口标准) 返回的字段相对精简
CSV_HEADERS = [
    "id",           # 模型 ID，例如 'deepseek-chat'
    "created",      # 创建时间的 Unix 时间戳
    "object",       # 对象类型，通常是 'model'
    "owned_by",     # 所属方，通常是 'deepseek'
]

def fetch_and_save_deepseek_models():
    """
    通过 OpenAI SDK 格式从 DeepSeek 获取可用模型列表，
    将原始数据保存到 TXT，将结构化数据保存到 CSV。
    """
    try:
        # 使用 DeepSeek 的 Base URL 和 API Key 初始化客户端
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        
        print("开始获取 DeepSeek 模型...")
        print(f" > 原始数据将保存至: {TXT_FILENAME}")
        print(f" > CSV 表格将保存至: {CSV_FILENAME}")

        with open(TXT_FILENAME, "w", encoding="utf-8") as f_txt, \
             open(CSV_FILENAME, "w", encoding="utf-8", newline="") as f_csv:

            # 初始化 CSV 写入器
            writer = csv.DictWriter(f_csv, fieldnames=CSV_HEADERS)
            writer.writeheader()

            model_count = 0
            
            # 获取模型列表并遍历
            # client.models.list() 返回一个 SyncPage[Model] 对象，我们遍历它
            models_page = client.models.list()
            for m in models_page:
                model_count += 1
                
                # --- 1. 写入 TXT (原始数据) ---
                # 使用 str(m) 保留对象的完整字符串表示
                f_txt.write("===================\n")
                f_txt.write(str(m) + "\n")

                # --- 2. 写入 CSV (结构化视图) ---
                row_data = {}
                for header in CSV_HEADERS:
                    # 使用 getattr 安全提取属性
                    value = getattr(m, header, None)
                    row_data[header] = value
                
                writer.writerow(row_data)
                
                # 在控制台打印简化的进度信息
                m_id = getattr(m, 'id', 'Unknown')
                m_owner = getattr(m, 'owned_by', 'Unknown')
                print(f"[{model_count}] 已处理: {m_id:<25} (Owner: {m_owner})")

        print("-" * 60)
        print(f"✅ 成功！共找到 {model_count} 个模型。")

    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    fetch_and_save_deepseek_models()