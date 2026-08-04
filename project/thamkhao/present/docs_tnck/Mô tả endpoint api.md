

###  Mô tả API endpoint
- **Base URL**:  
  `https://api.tinnhanhchungkhoan.vn/api`
- **Endpoint**:  
  `GET /morenews-zone-{zone}-{page}.html?phrase={TICKER}`
- **Tham số**:
  - `ticker`: Mã cổ phiếu
  - `zone`: Zone ID, (mặc định `4` = Thông tin doanh nghiệp, các tham số ID khác nhau được liệt kê ở phần sau.
  - `page`: Số tran)g
  - `phrase`:Giá trị `phrase` được gửi lên server. Đây là tham số filter server-side: - `GET /morenews-zone-4-2.html?phrase=TV2`
  - Mô tả
		```json
		{
		  "ticker": "TV2",
		  "zone": 4,
		  "page": 2,
		  "requested_phrase": "TV2",
		  "raw_json": { ...... }
		}
		```
- **Header**:
  - `User-Agent`: Browser agent thật (Chrome trên Windows).
  - `Accept`: `application/json, text/plain, */*`
  - `Referer`: `https://www.tinnhanhchungkhoan.vn/`
- **Response**:
  - Log thô respone API
	  - mô tả
	    ```JSON        dict:
            {
              "meta": {...},           # Thông tin cấu hình/chạy
              "responses": [           # Danh sách response raw
                {
                  "ticker": "...",
                  "zone": 4,
                  "page": 2,
                  "requested_phrase": "...",
                  "raw_json": { ... }  # JSON gốc từ API
                },
                ...
              ]
            }
	    ```
- Xử lý để trích xuất thông tin bài đăng.
	- Xử lý:
		- Flatten data.contents cho từng bài đăng
			- Xác định records -> responses[0].raw_json.data.contents[0] -> 1record
	- output: C:\Users\anpt\Downloads\evaluate_performance_chartpattern\openning\export\final\tnck_raw_api\output\all_articles_by_ticker_20260212_163152.csv
	- ```json
{
  "ticker": "TV2",
  "content_id": 384814,
  "title": "Dịch vụ Phân phối Tổng hợp Dầu khí (PSD) vượt 40% mục tiêu lợi nhuận 2025",
  "sub_title": "",
  "description": "(ĐTCK) Năm 2025, CTCP Dịch vụ Phân phối Tổng hợp Dầu khí (Petrosetco Distribution, mã PSD) ghi nhận 143,1 tỷ đồng lợi nhuận sau thuế, tăng 73% so với năm trước và vượt 40% mục tiêu năm.",
  "date_unix": 1770108462,
  "date_str": "2026-02-03 15:47:42",
  "update_time_unix": 1770108462,
  "update_time_str": "2026-02-03 15:47:42",
  "full_url": "https://www.tinnhanhchungkhoan.vn/dich-vu-phan-phoi-tong-hop-dau-khi-psd-vuot-40-muc-tieu-loi-nhuan-2025-post384814.html",
  "relative_url": "/dich-vu-phan-phoi-tong-hop-dau-khi-psd-vuot-40-muc-tieu-loi-nhuan-2025-post384814.html",
  "avatar_url": "https://image.tinnhanhchungkhoan.vn/w200/Uploaded/2026/xvrhgenatpx97/2026_02_03/492389603-...-n-8553-4165.jpg",
  "avatar_description": "",
  "source": "",
  "source_url": "",
  "zone_id": 4,
  "zone_name": "Thông tin doanh nghiệp",
  "zone_url": "/thong-tin-doanh-nghiep/",
  "related_tickers": "BMI,C4G,DL1,FPT,GCF,GMD,HUT,IDC,ITD,MBB,MWG,PAC,PC1,PVD,PVS,SHB,SIP,STH,TIP,TV2,VGT"
}
```

