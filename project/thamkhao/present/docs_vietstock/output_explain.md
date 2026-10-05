## 4. OUTPUT - Dữ liệu raw trả về từ API

### 4.1 Cấu trúc JSON response cho nhóm Article

API trả về **một JSON array**, mỗi phần tử là một object với **18 trường cố định**.

```jsonc
// RAW RESPONSE từ TopPageArticle (channelid=733, item=1)
[
    {
        "ArticleID": 1402828,
        "ArticleType": 1,
        "ChannelID": 733,
        "CommentCount": 0,
        "FullName": "Informer",
        "Head": "Đợt tăng của giá bạc vừa qua là hiếm gặp. Ngay sau khi...",
        "HeadImageUrl": "https://image.vietstock.vn/2026/02/11/vietstock_s_...",
        "Icon": null,
        "ImageView": "https://image.vietstock.vn/2026/02/11/vietstock_s_...",
        "MenuName": "Vàng và kim loại quý",
        "PostPersonalID": 12345,
        "PublishTime": "/Date(1707471000000)/",
        "Sponsor": null,
        "SponsorImg": null,
        "Title": "Bạc tăng phi mã rồi 'sập', có phải đã bị 'làm giá' quá mức?",
        "TotalView": 1520,
        "URL": "/tai-chinh/chung-khoan-748/bac-tang-phi-ma-roi-sap-1402828.htm",
        "VideoType": 0
    }
]
```

### 4.2 Bảng giải thích các trường RAW

| Trường           | Kiểu           | Mô tả                                                | Ví dụ                              |
| ------------------ | --------------- | ------------------------------------------------------ | ------------------------------------ |
| `ArticleID`      | `int`         | ID duy nhất của bài viết                           | `1402828`                          |
| `ArticleType`    | `int`         | Loại bài viết (1 = bài thường)                   | `1`                                |
| `ChannelID`      | `int`         | ID chuyên mục chứa bài                             | `733`                              |
| `CommentCount`   | `int`         | Số bình luận                                        | `0`                                |
| `FullName`       | `string`      | Tên tác giả                                         | `"Informer"`                       |
| `Head`           | `string`      | Tóm tắt / sapo bài viết                            | `"Đợt tăng của giá bạc..."`  |
| `HeadImageUrl`   | `string`      | URL ảnh đại diện (high-res)                        | `"https://image.vietstock.vn/..."` |
| `Icon`           | `null`        | Icon đặc biệt (thường null)                       | `null`                             |
| `ImageView`      | `string`      | URL ảnh thumbnail                                     | `"https://image.vietstock.vn/..."` |
| `MenuName`       | `string`      | Tên chuyên mục / chuyên đề                       | `"Vàng và kim loại quý"`       |
| `PostPersonalID` | `int`         | ID tác giả trong hệ thống                          | `12345`                            |
| `PublishTime`    | `string`      | **Thời gian đăng** (định dạng .NET)        | `"/Date(1707471000000)/"`          |
| `Sponsor`        | `null\|string` | Nhà tài trợ (nếu có)                              | `null`                             |
| `SponsorImg`     | `null\|string` | Ảnh nhà tài trợ                                    | `null`                             |
| `Title`          | `string`      | Tiêu đề bài viết                                  | `"Bạc tăng phi mã..."`          |
| `TotalView`      | `int`         | Tổng lượt xem                                       | `1520`                             |
| `URL`            | `string`      | **Đường dẫn tương đối** đến bài viết | `"/tai-chinh/chung-khoan-748/..."` |
| `VideoType`      | `int`         | Loại video (0 = không có video)                     | `0`                                |
