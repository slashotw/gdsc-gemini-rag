from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import googlemaps
import google.generativeai as genai
from dotenv import load_dotenv
import os
import logging
from typing import List, Dict
import json
import re

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 載入環境變數
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 初始化 FastAPI
app = FastAPI(title="約會寶 APP")

# 設置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源，生產環境中應限制
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

# 初始化 Google Maps 客戶端
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# 初始化 Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro")

# 請求模型
class KeywordSearchRequest(BaseModel):
    keywords: List[str]
    location: str

# 回應模型
class KeywordSearchResponse(BaseModel):
    itinerary: str  # 完整行程計劃
    places: Dict[str, List[Dict]]  # 按類別分類的地點

# Google Places 搜尋函數
def google_places_search(query: str, location: str) -> List[Dict]:
    try:
        # 先嘗試將位置轉換為經緯度坐標
        geocode_result = gmaps.geocode(location)
        
        if geocode_result and len(geocode_result) > 0:
            # 使用地理編碼結果的位置坐標
            location_coords = (
                geocode_result[0]['geometry']['location']['lat'],
                geocode_result[0]['geometry']['location']['lng']
            )
            logger.info(f"搜尋位置 '{location}' 解析為坐標: {location_coords}")
            
            places_result = gmaps.places(
                query=query,
                location=location_coords,
                radius=10000,  # 10km 範圍
                language="zh-TW"
            )
        else:
            # 如果無法進行地理編碼，使用字符串位置
            logger.warning(f"無法解析位置 '{location}' 為坐標，使用文字搜尋")
            places_result = gmaps.places(
                query=f"{query} in {location}",
                language="zh-TW"
            )
            
        logger.info(f"搜尋 '{query}' 於 '{location}' 返回 {len(places_result.get('results', []))} 個結果")
        return places_result.get("results", [])
    except Exception as e:
        logger.error(f"Google Places API error: {str(e)}")
        return []

# Gemini Function Calling 工具定義
tools = [
    {
        "name": "google_places_search",
        "description": "Search for places using Google Places API based on a query and location.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query for the place."},
                "location": {"type": "string", "description": "The location to search around."}
            },
            "required": ["query", "location"]
        }
    }
]

# Gemini 調用函數
async def call_gemini(prompt: str, tools: List[Dict] = None) -> Dict:
    try:
        logger.info(f"Calling Gemini with prompt: {prompt[:100]}...")
        response = model.generate_content(
            prompt,
            tools=tools if tools else None,
            generation_config={"max_output_tokens": 1000}
        )
        logger.info(f"Gemini response type: {type(response)}")
        
        if not hasattr(response, 'candidates') or not response.candidates:
            logger.error("No candidates in Gemini response")
            return {"parts": [{"text": "{}"}]}
            
        logger.info(f"Response candidate type: {type(response.candidates[0].content)}")
        return response.candidates[0].content
    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Gemini API error: {str(e)}")

# /keyword_search 端點
@app.post("/keyword_search", response_model=KeywordSearchResponse)
async def keyword_search(request: KeywordSearchRequest):
    try:
        # 1. Gemini 整理關鍵字
        prompt = f"""
        用戶計劃在{request.location}度過一天，希望行程中能包含以下類型的地點：{', '.join(request.keywords)}。
        請針對這些關鍵字，為每一個關鍵字生成 2-3 個具體的搜尋詞，以便用 Google Places API 尋找適合的地點。
        
        例如，如果關鍵字是"咖啡廳"和"桌遊店"，則可能的搜尋詞為：
        - 咖啡廳類：台北特色咖啡廳、台北網美咖啡廳、台北早午餐咖啡廳
        - 桌遊店類：台北桌遊店、台北桌遊體驗館、台北桌遊咖啡

        請確保每個關鍵字至少有 2 個對應的搜尋詞，且包含地點"{request.location}"。
        
        回傳格式為 JSON：
        ```json
        {{
            "search_queries": {{
                "關鍵字1": ["搜尋詞1", "搜尋詞2", ...],
                "關鍵字2": ["搜尋詞1", "搜尋詞2", ...],
                ...
            }}
        }}
        ```
        """
        gemini_response = await call_gemini(prompt)
        # 假設 Gemini 回傳 JSON 字符串，解析為 Python 字典
        try:
            logger.info(f"Gemini response: {gemini_response}")
            # 檢查 gemini_response 的結構
            if hasattr(gemini_response, 'parts') and gemini_response.parts:
                response_text = gemini_response.parts[0].text
                logger.info(f"Response text: {response_text}")
                
                # 處理回傳可能包含的 Markdown 格式
                if "```json" in response_text:
                    # 提取 ```json 和 ``` 之間的 JSON 內容
                    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
                    if json_match:
                        json_content = json_match.group(1)
                        logger.info(f"Extracted JSON: {json_content}")
                        search_queries_data = json.loads(json_content)
                    else:
                        # 如果無法提取，嘗試直接解析
                        search_queries_data = json.loads(response_text)
                else:
                    # 直接嘗試解析
                    search_queries_data = json.loads(response_text)
                    
                search_queries = search_queries_data.get("search_queries", {})
            else:
                logger.error("Unexpected Gemini response structure")
                response_text = str(gemini_response)
                logger.info(f"Raw response: {response_text}")
                # 嘗試直接從響應文本中提取查詢詞
                search_queries = {}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}, response: {gemini_response}")
            # 嘗試備用方案
            search_queries = {}

        if not search_queries:
            # 如果無法從 Gemini 獲取搜尋詞，使用原始關鍵字
            search_queries = {keyword: [f"{keyword} {request.location}"] for keyword in request.keywords}
            logger.info(f"使用預設搜尋詞：{search_queries}")

        # 2. 逐項調用 Google Places API
        category_results = {}  # 按類別存儲結果
        all_place_ids = set()  # 追蹤所有的地點 ID
        
        for category, queries in search_queries.items():
            logger.info(f"處理類別 '{category}'")
            category_places = []
            seen_place_ids = set()  # 僅用於當前類別的去重
            
            # 限制每個類別的搜尋查詢數量
            max_queries = min(3, len(queries))
            logger.info(f"使用前 {max_queries} 個查詢詞（共 {len(queries)} 個）進行搜尋")
            
            for query in queries[:max_queries]:
                results = google_places_search(query, request.location)
                
                # 添加不重複的結果到當前類別
                for place in results:
                    place_id = place.get("place_id")
                    if place_id and place_id not in seen_place_ids:
                        seen_place_ids.add(place_id)
                        category_places.append(place)
                        all_place_ids.add(place_id)  # 添加到全局跟踪集
            
            # 限制每個類別最多保留 5 個結果
            category_places = category_places[:5]
            category_results[category] = category_places
            logger.info(f"類別 '{category}' 搜尋完成，共找到 {len(category_places)} 個地點")
        
        logger.info(f"所有類別搜尋完成，共找到 {len(all_place_ids)} 個不重複地點")
        
        # 3. 為每個類別準備摘要信息
        categories_summary = {}
        for category, places in category_results.items():
            places_summary = [
                {
                    "name": place.get("name"),
                    "address": place.get("formatted_address"),
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "place_id": place.get("place_id"),
                    "types": place.get("types", [])
                }
                for place in places
            ]
            categories_summary[category] = places_summary

        # 4. Gemini 生成行程計劃
        itinerary_prompt = f"""
        用戶希望在{request.location}度過一天的約會，行程中需要包含以下類型的地點：{', '.join(request.keywords)}。
        
        根據搜尋結果，我已為每個類別找到了幾個推薦地點：
        
        {json.dumps(categories_summary, ensure_ascii=False, indent=2)}
        
        請根據這些地點，規劃一個完整的一日行程。行程應該：
        1. 包含早上、中午、下午和晚上的活動
        2. 每個指定類別的地點至少包含一個
        3. 考慮地點之間的合理順序，避免來回奔波
        4. 為每個地點提供 1-2 句推薦理由或亮點
        
        格式要求：
        - 以「行程規劃：台北一日約會」為標題
        - 使用時間線格式（如：9:00-10:30）
        - 每個地點後附上簡短推薦理由
        - 總字數控制在 300-400 字之間
        - 語言為繁體中文
        """
        
        itinerary_response = await call_gemini(itinerary_prompt)
        try:
            if hasattr(itinerary_response, 'parts') and itinerary_response.parts:
                itinerary = itinerary_response.parts[0].text
            else:
                itinerary = str(itinerary_response)
                if not itinerary:
                    itinerary = f"無法生成{request.location}一日約會行程規劃"
        except Exception as e:
            logger.error(f"Error extracting itinerary: {str(e)}")
            itinerary = f"無法生成{request.location}一日約會行程規劃"

        # 5. 處理回傳的地點數據
        places_data = {}
        for category, places in category_results.items():
            places_data[category] = [
                {
                    "name": place.get("name", ""),
                    "address": place.get("formatted_address", ""),
                    "rating": place.get("rating", 0),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "place_id": place.get("place_id", ""),
                    "location": place.get("geometry", {}).get("location", {}) if place.get("geometry") else {},
                    "types": place.get("types", []),
                    "photos": place.get("photos", [])
                }
                for place in places
            ]
            
        # 6. 回傳結果
        return KeywordSearchResponse(
            itinerary=itinerary,
            places=places_data
        )

    except Exception as e:
        logger.error(f"Error in keyword_search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 啟動時檢查
@app.on_event("startup")
async def startup_event():
    if not GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY not set")
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set")
        raise RuntimeError("GEMINI_API_KEY not set")