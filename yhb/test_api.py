import unittest
import requests
import json
import time
from typing import List, Dict

class TestDatePlannerAPI(unittest.TestCase):
    """約會寶 APP API 測試類"""
    
    BASE_URL = "http://localhost:9000"
    ENDPOINT = "/keyword_search"
    
    def setUp(self):
        """測試前的準備工作"""
        self.test_cases = [
            {
                "location": "台北",
                "keywords": ["咖啡廳", "電影院", "餐廳"]
            },
            {
                "location": "台中",
                "keywords": ["公園", "書店", "甜點店"]
            },
            {
                "location": "高雄",
                "keywords": ["夜市", "海灘", "酒吧"]
            },
            {
                "location": "新竹",
                "keywords": ["科學園區", "桌遊店", "美術館"]
            },
            {
                "location": "台南",
                "keywords": ["古蹟", "小吃", "文創園區"]
            }
        ]
    
    def test_keyword_search_endpoint(self):
        """測試關鍵字搜尋端點"""
        for i, test_case in enumerate(self.test_cases, 1):
            with self.subTest(test_case=test_case):
                print(f"\n===== 測試 #{i}: {test_case['location']} - {', '.join(test_case['keywords'])} =====")
                
                # 構建請求數據
                request_data = {
                    "keywords": test_case["keywords"],
                    "location": test_case["location"]
                }
                
                # 發送 POST 請求
                try:
                    start_time = time.time()
                    response = requests.post(
                        f"{self.BASE_URL}{self.ENDPOINT}", 
                        json=request_data,
                        timeout=60  # 設置較長的超時時間，因為 AI 生成可能需要時間
                    )
                    end_time = time.time()
                    
                    # 檢查狀態碼
                    self.assertEqual(response.status_code, 200, f"API 返回錯誤狀態碼: {response.status_code}")
                    
                    # 解析返回數據
                    response_data = response.json()
                    
                    # 檢查返回的數據結構
                    self.assertIn("itinerary", response_data, "返回數據中缺少 'itinerary' 欄位")
                    self.assertIn("places", response_data, "返回數據中缺少 'places' 欄位")
                    
                    # 檢查行程內容不為空
                    self.assertTrue(len(response_data["itinerary"]) > 0, "行程內容為空")
                    
                    # 檢查至少有一個地點類別
                    self.assertTrue(len(response_data["places"]) > 0, "沒有返回任何地點類別")
                    
                    # 檢查每個類別是否有地點
                    for category, places in response_data["places"].items():
                        self.assertTrue(len(places) > 0, f"類別 '{category}' 沒有地點")
                        
                        # 檢查地點數據結構
                        for place in places:
                            self.assertIn("name", place, "地點缺少名稱")
                            self.assertIn("address", place, "地點缺少地址")
                    
                    # 輸出響應時間和結果摘要
                    print(f"響應時間: {end_time - start_time:.2f} 秒")
                    print(f"行程長度: {len(response_data['itinerary'])} 字元")
                    print(f"地點類別數: {len(response_data['places'])}")
                    
                    # 輸出行程的前100個字符
                    itinerary_preview = response_data["itinerary"][:100] + "..." if len(response_data["itinerary"]) > 100 else response_data["itinerary"]
                    print(f"行程預覽: {itinerary_preview}")
                    
                    # 輸出每個類別的地點數量
                    for category, places in response_data["places"].items():
                        print(f"- {category}: {len(places)} 個地點")
                    
                    # 在測試之間暫停一下，避免 API 限制
                    time.sleep(2)
                    
                except requests.RequestException as e:
                    self.fail(f"API 請求失敗: {str(e)}")
                except json.JSONDecodeError as e:
                    self.fail(f"API 返回格式不正確: {str(e)}")

if __name__ == "__main__":
    unittest.main() 