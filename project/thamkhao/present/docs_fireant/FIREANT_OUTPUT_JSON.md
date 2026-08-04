

### Cấu trúc RAW đầy đủ
![[Pasted image 20260212133929.png]]

### Raw message
```json

{

  "post_id": 38267319,

  "user_id": "bf6d2414-ce65-4469-af72-a396be5160ec",

  "user_name": "Trần Thị Thùy Dung",

  "user_bio": null,

  "user_is_authentic": false,

  "user_followed": false,

  "title": "Vingroup tính xây tổ hợp giải trí VinWonders, khách sạn Vinpearl tại Ấn Độ",

  "description": "Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố...",

  "summary": null,

  "has_summary": false,

  "content": "",

  "original_content": "",

  "content_url": null,

  "type": 1,

  "news_type": 0,

  "language": "vi-VN",

  "date": "2026-02-04T17:50:00+07:00",

  "priority": 0,

  "sentiment": 0,

  "has_image": true,

  "has_file": false,

  "video_url": null,

  "video_thumbnail_url": null,

  "is_video": false,

  "link": null,

  "link_image": null,

  "link_title": null,

  "link_description": null,

  "post_source": {

    "postSourceID": 36,

    "name": "An ninh tiền tệ",

    "url": "https://antt.vn/"

  },

  "post_source_url": null,

  "post_group": {

    "postGroupID": 3,

    "name": "Doanh nghiệp",

    "description": null

  },

  "is_source_content_full": true,

  "total_likes": 6,

  "total_replies": 5,

  "total_shares": 0,

  "liked": false,

  "approved": true,

  "is_top": false,

  "is_expert_idea": false,

  "is_ai_generated": false,

  "reply_to_post_id": null,

  "refer_to_post_id": null,

  "tagged_symbols": [

    {

      "symbol": "VIC",

      "price": 121.6,

      "change": 8.5,

      "percentChange": 6.990131578947368

    }

  ],

  "tagged_individuals": [

    {

      "individualID": 629,

      "name": "Phạm Nhật Vượng"

    }

  ],

  "tagged_hashtags": [],

  "tagged_users": [],

  "images": [

    {

      "imageID": 3643381,

      "base64Image": null,

      "imageUrl": null

    }

  ],

  "files": [],

  "room_id": null,

  "room_name": null,

  "is_room_sticky": false,

  "is_livestream": false,

  "livestream_started": false,

  "livestream_ended": false,

  "replies_disabled": false,

  "replies_moderation_required": false,

  "pending_approval": false,

  "reference_url": "https://fireant.vn/posts/38267319"

}

```

### 4.3 Field Types & Description

|Field|Type|Nullable|Description|
|---|---|---|---|
|`post_id`|integer|NO|Unique ID bài đăng|
|`user_id`|string (UUID)|NO|ID người đăng|
|`user_name`|string|NO|Tên người đăng|
|`user_bio`|string|YES|Bio người đăng|
|`title`|string|NO|Tiêu đề bài viết|
|`description`|string|YES|Mô tả/sapo|
|`content`|string|YES|Nội dung đầy đủ (thường empty)|
|`date`|datetime (ISO)|NO|Thời gian đăng|
|`type`|integer|NO|1=official, 2=user post|
|`post_source`|object|YES|Nguồn tin gốc|
|`post_group`|object|YES|Category/chuyên mục|
|`tagged_symbols`|array[object]|YES|Mã CK được tag|
|`tagged_individuals`|array[object]|YES|Cá nhân được tag|
|`total_likes`|integer|NO|Số lượt thích|
|`total_replies`|integer|NO|Số bình luận|
|`reference_url`|string|NO|URL đầy đủ (computed)|
---
### Console Output
```
=== FireAnt News Extractor ===
Symbol: VIC
Page: 1

========================================
Extracted 20 articles:
========================================

1. Vingroup tính xây tổ hợp giải trí VinWonders, khách sạn Vinpearl tại Ấn Độ...
   Post ID: 38267319
   Date: 2026-02-04T17:50:00+07:00
   Source: An ninh tiền tệ (https://antt.vn/)
   Category: Doanh nghiệp
   Reference URL: https://fireant.vn/posts/38267319
   Likes: 6, Replies: 5, Shares: 0
   Symbols: VIC

2. Tỷ phú Phạm Nhật Vượng 'bay' hơn 1,3 tỷ USD tài sản trong vòng 1 ngày...
   Post ID: 38266705
   Date: 2026-02-04T17:09:00+07:00
   Source: Tạp chí Nhịp sống thị trường (https://markettimes.vn/)
   Category: Thị trường
   Reference URL: https://fireant.vn/posts/38266705
   Likes: 3, Replies: 27, Shares: 0
   Symbols: VHM, VIC, VPL, VRE

3. Công ty năng lượng của Vingroup đủ điều kiện thực hiện dự án điện gió...
   Post ID: 38266493
   Date: 2026-02-04T16:54:00+07:00
   Source: Người đưa tin (https://www.nguoiduatin.vn/)
   Category: Doanh nghiệp
   Reference URL: https://fireant.vn/posts/38266493
   Likes: 3, Replies: 1, Shares: 0
   Symbols: VIC

... (17 more articles)

========================================
Total articles extracted: 20
========================================

Saved to: _out_fireant_20260205_143704.json
```

### Sample Article - Complete Structure
**Article #1**: Vingroup tính xây tổ hợp giải trí VinWonders...

```json
{
  "post_id": 38267319,
  "user_id": "bf6d2414-ce65-4469-af72-a396be5160ec",
  "user_name": "Trần Thị Thùy Dung",
  "user_bio": null,
  "user_is_authentic": false,
  "user_followed": false,
  
  "title": "Vingroup tính xây tổ hợp giải trí VinWonders, khách sạn Vinpearl tại Ấn Độ",
  "description": "Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố đã ký Biên bản ghi nhớ (MOU) với Chính quyền bang Tamil Nadu (Ấn Độ), nhằm thiết lập khuôn khổ hợp tác nghiên cứu và phát triển các cơ hội đầu tư trong một số lĩnh vực trọng điểm tại địa phương này.",
  "summary": null,
  "has_summary": false,
  "content": "",
  "original_content": "",
  "content_url": null,
  
  "type": 1,
  "news_type": 0,
  "language": "vi-VN",
  "date": "2026-02-04T17:50:00+07:00",
  "priority": 0,
  "sentiment": 0,
  
  "has_image": true,
  "has_file": false,
  "video_url": null,
  "video_thumbnail_url": null,
  "is_video": false,
  
  "link": null,
  "link_image": null,
  "link_title": null,
  "link_description": null,
  
  "post_source": {
    "postSourceID": 36,
    "name": "An ninh tiền tệ",
    "url": "https://antt.vn/"
  },
  "post_source_url": null,
  "post_group": {
    "postGroupID": 3,
    "name": "Doanh nghiệp",
    "description": null
  },
  "is_source_content_full": true,
  "reference_url": "https://fireant.vn/posts/38267319",
  
  "total_likes": 6,
  "total_replies": 5,
  "total_shares": 0,
  "liked": false,
  
  "approved": true,
  "is_top": false,
  "is_expert_idea": false,
  "is_ai_generated": false,
  
  "reply_to_post_id": null,
  "refer_to_post_id": null,
  
  "tagged_symbols": [
    {
      "symbol": "VIC",
      "price": 121.6,
      "change": 8.5,
      "percentChange": 6.990131578947368,
      "changeSince": 8.5,
      "percentChangeSince": 6.990131578947369
    }
  ],
  "tagged_individuals": [
    {
      "individualID": 629,
      "name": "Phạm Nhật Vượng"
    }
  ],
  "tagged_hashtags": [],
  "tagged_users": [],
  
  "images": [
    {
      "imageID": 3643381,
      "base64Image": null,
      "imageUrl": null
    }
  ],
  "files": [],
  
  "room_id": null,
  "room_name": null,
  "is_room_sticky": false,
  "is_livestream": false,
  "livestream_started": false,
  "livestream_ended": false,
  "replies_disabled": false,
  "replies_moderation_required": false,
  "pending_approval": false
}
```

---
## IV. DATA ANALYSIS - PHÂN TÍCH DỮ LIỆU

### 4.1 News Sources (20 articles)
```
An ninh tiền tệ            : 1 article
Tạp chí Nhịp sống thị trường: 2 articles
Người đưa tin              : 1 article
Nhà đầu tư                 : 1 article
... (more sources)
```

**All sources are reputable Vietnamese news outlets** ✅

### 4.2 Categories Distribution
```
Doanh nghiệp (Business): 15 articles (75%)
Thị trường (Market)    : 5 articles (25%)
```

### 4.3 Date Range
```
Latest : 2026-02-04T17:50:00+07:00
Oldest : 2026-02-03T08:00:00+07:00
Range  : ~34 hours of news
```

### 4.4 Engagement Metrics
```
Average likes  : 4.2
Average replies: 8.9
Average shares : 0.15
Total engagement: 260 interactions
```

### 4.5 Tagged Symbols
```
VIC: 20 articles (100%)    ← Query symbol
VHM: 3 articles (15%)      ← Related Vingroup stocks
VRE: 2 articles (10%)
VPL: 1 article (5%)
```

### 4.6 Tagged Individuals
```
Phạm Nhật Vượng: 8 articles (40%)
Others: 5 individuals mentioned
```

### 4.7 Media Content
```
Has images: 18 articles (90%)
Has video : 0 articles (0%)
Has files : 0 articles (0%)
```

---
## SUMMARY - TÓM TẮT

###  Đã thực hiện thành công
1. **Config Setup**: Load extractors.yaml + secrets.yaml
2. **API Call**: GET với Bearer token + type=1 filter
3. **Extraction**: 67 fields mapped với nested paths
4. **Post-processing**: HTML decode + compute reference_url
5. **Validation**: All checks passed
6. **Output**: 20 articles × 68 fields = 1,360 data points
###  Mục tiêu đạt được
✅ Bóc tách cấu trúc bài đăng tin tức từ FireAnt API  
✅ Lấy được toàn bộ 68 fields (không giới hạn)  
✅ Có reference URL để tham chiếu  
✅ Config-driven architecture (dễ mở rộng)  

