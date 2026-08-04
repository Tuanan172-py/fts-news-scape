# CafeF News Crawler - Output Data Structure

## Mục đích

Document này mô tả **cấu trúc dữ liệu nguyên bản (RAW)** được trả về từ hệ thống CafeF News Crawler, **không có sắp xếp hay modify gì cả**, chỉ trả về nguyên bản theo đối tượng cổ phiếu từ danh sách recommendations.

## Nguồn dữ liệu

### 1. CafeF API Response

**Endpoint:** `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx`

**Raw API Response:**
```json
{
  "Success": true,
  "Data": [
    {
      "Title": "Hoà Phát (HPG): Quý 4 lãi 5.239 tỷ đồng, cả năm 2025 đạt 23.200 tỷ đồng",
      "LinkDetail": "/du-lieu/HPG-2394741/hoa-phat-hpg-quy-4-lai-5239-ty-dong-ca-nam-2025-dat-23200-ty-dong.chn",
      "DeployDate": "/Date(1738303980000+0700)/",
      "NewsType": 0,
      "Summary": "Công ty Cổ phần Tập đoàn Hoà Phát công bố kết quả kinh doanh quý 4 và cả năm 2025..."
    },
    {
      "Title": "...",
      "LinkDetail": "...",
      "DeployDate": "/Date(1738217580000+0700)/",
      "NewsType": 0,
      "Summary": "..."
    }
  ]
}
```

### 2. Article HTML Structure

**URL:** `https://cafef.vn{LinkDetail}`

**Raw HTML Elements Extracted:**
```html
<h1 class="title">Tiêu đề bài viết</h1>

<h2 class="sapo">Mô tả ngắn của bài viết (sapo/subtitle)</h2>

<span class="pdate">08/02/2026 10:30</span>

<div id="mainContent">
  <p>Đoạn văn 1 của bài viết...</p>
  <p>Đoạn văn 2...</p>
  
  <table>
    <tr>
      <th>Chỉ tiêu</th>
      <th>Q4/2025</th>
      <th>Q4/2024</th>
    </tr>
    <tr>
      <td>Doanh thu</td>
      <td>35,000 tỷ</td>
      <td>30,000 tỷ</td>
    </tr>
  </table>
  
  <p>Đoạn văn tiếp theo...</p>
</div>

<p style="text-align: right;">Theo CafeF</p>
```

## Output Data Structure (RAW JSON)

### Complete Article Object

Đây là cấu trúc **100% nguyên bản**, không modify, không sắp xếp:

```json
{
  "ticker": "HPG",
  "source": "CafeF",
  "url": "https://cafef.vn/du-lieu/HPG-2394741/hoa-phat-hpg-quy-4-lai-5239-ty-dong-ca-nam-2025-dat-23200-ty-dong.chn",
  
  "title": "Hoà Phát (HPG): Quý 4 lãi 5.239 tỷ đồng, cả năm 2025 đạt 23.200 tỷ đồng",
  
  "subtitle": "Công ty Cổ phần Tập đoàn Hoà Phát công bố kết quả kinh doanh quý 4 và cả năm 2025 với doanh thu thuần đạt 35.000 tỷ đồng trong quý 4.",
  
  "publish_time": "08/02/2026 10:30",
  
  "author": "Theo CafeF",
  
  "content_html": "<div id=\"mainContent\"><p>Công ty Cổ phần Tập đoàn Hoà Phát...</p><table><tr><th>Chỉ tiêu</th>...</tr></table><p>...</p></div>",
  
  "paragraphs": [
    "Công ty Cổ phần Tập đoàn Hoà Phát công bố kết quả kinh doanh quý 4 và cả năm 2025 với doanh thu thuần đạt 35.000 tỷ đồng trong quý 4.",
    "Lợi nhuận sau thuế quý 4 đạt 5.239 tỷ đồng, tăng 12% so với cùng kỳ năm trước.",
    "Cả năm 2025, tập đoàn ghi nhận doanh thu 132.000 tỷ đồng và lợi nhuận 23.200 tỷ đồng.",
    "..."
  ],
  
  "tables": [
    [
      ["Chỉ tiêu", "Q4/2025", "Q4/2024", "Tăng/Giảm"],
      ["Doanh thu", "35,000 tỷ", "30,000 tỷ", "+16.7%"],
      ["Lợi nhuận", "5,239 tỷ", "4,678 tỷ", "+12.0%"],
      ["EPS", "3,200 đồng", "2,850 đồng", "+12.3%"]
    ]
  ],
  
  "date": "2026-02-08T10:30:00",
  
  "api_metadata": {
    "Title": "Hoà Phát (HPG): Quý 4 lãi 5.239 tỷ đồng, cả năm 2025 đạt 23.200 tỷ đồng",
    "LinkDetail": "/du-lieu/HPG-2394741/hoa-phat-hpg-quy-4-lai-5239-ty-dong-ca-nam-2025-dat-23200-ty-dong.chn",
    "DeployDate": "/Date(1738303980000+0700)/",
    "DeployDate_parsed": "2026-02-08T10:30:00",
    "NewsType": 0,
    "Summary": "Công ty Cổ phần Tập đoàn Hoà Phát công bố kết quả kinh doanh quý 4 và cả năm 2025..."
  }
}
```

## Field Definitions

### Top-Level Fields

| Field | Type | Source | Description | Nullable |
|-------|------|--------|-------------|----------|
| `ticker` | string | Parameter | Mã cổ phiếu được crawl | No |
| `source` | string | Constant | Luôn là "CafeF" | No |
| `url` | string | Constructed | Full URL bài viết (`https://cafef.vn` + `LinkDetail`) | No |
| `title` | string | HTML | Tiêu đề từ `<h1 class="title">` | Yes (null nếu không tìm thấy) |
| `subtitle` | string | HTML | Sapo từ `<h2 class="sapo">` | Yes |
| `publish_time` | string | HTML | Thời gian đăng từ `<span class="pdate">` | Yes |
| `author` | string | HTML | Tác giả từ `<p style="text-align: right;">` | Yes |
| `content_html` | string | HTML | Toàn bộ HTML từ `<div id="mainContent">` | Yes |
| `paragraphs` | array[string] | HTML | Tất cả text từ các thẻ `<p>` trong mainContent | Always array (có thể rỗng []) |
| `tables` | array[array[array]] | HTML | Tất cả tables từ mainContent dạng 2D array | Always array (có thể rỗng []) |
| `date` | ISO string | Parsed | Ngày đăng chuẩn hóa từ DeployDate | Yes |
| `api_metadata` | object | API | Metadata nguyên bản từ CafeF API | Always object |

### api_metadata Fields

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `Title` | string | API | Tiêu đề từ API response |
| `LinkDetail` | string | API | Relative URL từ API |
| `DeployDate` | string | API | Raw date string từ API (format: `/Date(timestamp+timezone)/`) |
| `DeployDate_parsed` | ISO string | Parsed | Parsed date từ DeployDate |
| `NewsType` | number | API | Loại tin (0 = tất cả) |
| `Summary` | string | API | Tóm tắt từ API |

## Data Characteristics

### 1. No Filtering
- **Không filter theo tháng**: Lấy tất cả dữ liệu từ API
- **Không filter theo NewsType**: Lấy tất cả loại tin
- **Không filter theo keywords**: Lấy 100% tin liên quan đến ticker

### 2. No Modification
- **Content HTML**: Giữ nguyên 100% HTML từ website
- **Paragraphs**: Giữ nguyên thứ tự và nội dung
- **Tables**: Giữ nguyên cấu trúc 2D array
- **API Metadata**: Giữ nguyên tất cả fields từ API

### 3. No Sorting
- **Database**: Thứ tự theo thời gian crawl
- **Paragraphs**: Thứ tự xuất hiện trong HTML
- **Tables**: Thứ tự xuất hiện trong HTML
- **Fields**: Thứ tự như trong code

### 4. Duplicate Handling
- **Check**: Dựa trên URL normalization
- **Strategy**: UPSERT (insert if not exist, skip if exist)
- **Keep**: Tin cũ (first occurrence)

## Example Output Files

### JSON

File: `news_cafef_10022026.json`

```json
[
  {
    "ticker": "HPG",
    "source": "CafeF",
    "url": "https://cafef.vn/du-lieu/HPG-2394741/...",
    "title": "...",
    "subtitle": "...",
    "publish_time": "...",
    "author": "...",
    "content_html": "...",
    "paragraphs": [...],
    "tables": [...],
    "date": "2026-02-08T10:30:00",
    "api_metadata": {...}
  },
  {
    "ticker": "VIC",
    "source": "CafeF",
    "url": "...",
    ...
  }
]
```

### CSV (Flattened)

File: `news_cafef_10022026.csv`

```csv
ticker,source,url,title,subtitle,publish_time,author,content_html,paragraphs,tables,date,api_metadata
HPG,CafeF,https://cafef.vn/...,Hoà Phát...,Công ty...,08/02/2026 10:30,Theo CafeF,"<div id=""mainContent"">...","[""Para 1"", ""Para 2""]","[[...]]",2026-02-08T10:30:00,"{""Title"": ""..."", ...}"
VIC,CafeF,...
```

### Excel

File: `news_cafef_10022026.xlsx`

Sheet: "CafeF News"

| ticker | source | url | title | subtitle | publish_time | author | content_html | paragraphs | tables | date | api_metadata |
|--------|--------|-----|-------|----------|--------------|--------|--------------|------------|--------|------|--------------|
| HPG | CafeF | https://... | Hoà Phát... | Công ty... | 08/02/2026 10:30 | Theo CafeF | &lt;div...&gt; | [...] | [[...]] | 2026-02-08T10:30:00 | {...} |
| VIC | CafeF | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

## Use Cases

### 1. Đọc và Parse JSON

```python
import json

# Load data
with open('news_cafef_10022026.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

# Access fields
for article in articles:
    print(f"Ticker: {article['ticker']}")
    print(f"Title: {article['title']}")
    print(f"URL: {article['url']}")
    print(f"Date: {article['date']}")
    
    # Access paragraphs
    for para in article['paragraphs']:
        print(f"  - {para}")
    
    # Access tables
    for table in article['tables']:
        for row in table:
            print(row)
    
    # Access API metadata
    print(f"API Summary: {article['api_metadata']['Summary']}")
```

### 2. Query bằng Pandas

```python
import pandas as pd
import json

# Load JSON vào DataFrame
with open('news_cafef_10022026.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
df = pd.DataFrame(data)

# Filter by ticker
hpg_news = df[df['ticker'] == 'HPG']

# Filter by date
df['date_parsed'] = pd.to_datetime(df['date'])
recent = df[df['date_parsed'] >= '2026-02-01']

# Count by ticker
ticker_counts = df['ticker'].value_counts()
```

### 3. Extract Tables

```python
# Get all tables from all articles
for article in articles:
    if article['tables']:
        print(f"\nTicker: {article['ticker']}")
        print(f"Title: {article['title']}")
        
        for i, table in enumerate(article['tables']):
            print(f"\nTable {i+1}:")
            for row in table:
                print('\t'.join(row))
```

## Technical Notes

### Date Format Handling

CafeF API trả về 2 loại format:
1. **With timezone**: `/Date(1738303980000+0700)/`
2. **Without timezone**: `/Date(1770597720000)/`

Parser tự động xử lý cả 2 format:
```python
timestamp_part = date_str.split('(')[1].split(')')[0]  # "1738303980000+0700" hoặc "1738303980000"
timestamp_ms = int(timestamp_part.split('+')[0])       # "1738303980000"
datetime_obj = datetime.fromtimestamp(timestamp_ms / 1000)
```

