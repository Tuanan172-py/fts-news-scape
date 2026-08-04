# RSS Protocols Reference
RSS viết tắt là Really Simple Syndication hoặc Rich Site Summary, đây là một giao thức chuẩn hóa dựa trên định dạng XML (eXtensible Markup language)

Mục đích cốt lõi của RSS là chia sẻ và phân phối nội dung web tự động (Syndication). Thay vì phải truy cập thủ công vào từng trang web, đọc từng bài báo để xem có tin gì mới, giao thức RSS cho phép website tự động xuất bản một tệp tin XML chứa danh sách các bài viết mới nhất.

## RSS 2.0 (Really Simple Syndication)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>VnExpress Kinh Doanh</title>
    <link>https://vnexpress.net/kinh-doanh</link>
    <description>Tin tức kinh doanh</description>
    <language>vi</language>
    <lastBuildDate>Fri, 24 Jul 2026 03:00:00 +0700</lastBuildDate>
    <item>
      <title>VN-Index vượt mốc 1.300 điểm</title>
      <link>https://vnexpress.net/vn-index-vuot-moc-1300-123.html</link>
      <description>Thị trường chứng khoán...</description>
      <pubDate>Fri, 24 Jul 2026 03:00:00 +0700</pubDate>
      <guid isPermaLink="true">https://vnexpress.net/vn-index-vuot-moc-1300-123.html</guid>
      <category>Chứng khoán</category>
      <author>Nguyễn Văn A</author>
    </item>
  </channel>
</rss>
```

**Key elements:**
- `<guid>` — unique identifier (prefer làm dedup key)
- `<pubDate>` — RFC 822 date
- `<description>` — thường chỉ là summary, không full content

---

## Atom (Khắt khe hơn RSS 2.0 để khắc phục sự lỏng lẻo)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Cafef</title>
  <link href="https://cafef.vn/rss/trang-chu.rss"/>
  <updated>2026-07-24T03:00:00+07:00</updated>
  <entry>
    <title>Cổ phiếu ngân hàng dẫn dắt thị trường</title>
    <link href="https://cafef.vn/co-phieu-ngan-hang-123.html"/>
    <id>urn:uuid:123e4567-e89b-12d3-a456-426614174000</id>
    <published>2026-07-24T03:00:00+07:00</published>
    <updated>2026-07-24T03:05:00+07:00</updated>
    <summary type="html">Cổ phiếu ngân hàng...</summary>
    <author><name>Minh Anh</name></author>
    <category term="Chứng khoán"/>
  </entry>
</feed>
```

**Khác RSS 2.0:**
- `<id>` — chuẩn UUID/URI (thay cho `<guid>`)
- Ngày tháng ISO 8601 (dễ parse hơn)
- `<summary>` có thể có `type="html"`

---

## RDF (RSS 1.0)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/">
  <channel rdf:about="https://example.com/rss">
    <title>Example</title>
    <link>https://example.com</link>
    <description>...</description>
    <items>
      <rdf:Seq>
        <rdf:li rdf:resource="https://example.com/article1"/>
      </rdf:Seq>
    </items>
  </channel>
  <item rdf:about="https://example.com/article1">
    <title>Article 1</title>
    <link>https://example.com/article1</link>
    <description>...</description>
  </item>
</rdf:RDF>
```

**Khác:**
- Cấu trúc phức tạp hơn (RDF namespace)
- Hầu như không dùng ở VN
- `feedparser` vẫn parse được

---

## Parse bằng feedparser

```python
import feedparser

feed = feedparser.parse('https://vnexpress.net/rss/kinh-doanh.rss')

# Format tự động detect
print(f'Feed: {feed.version}')  # rss20, atom10, rss10

for entry in feed.entries:
    print(f'Title: {entry.title}')
    print(f'Link: {entry.link}')
    print(f'Published: {entry.published_parsed}')  # struct_time
    print(f'Summary: {entry.summary}')
```

**Lưu ý:**
- `feed.bozo` = True nếu XML malformed (vẫn parse được)
- `feed.bozo_exception` — lỗi chi tiết
- Date tự động convert qua `entry.published_parsed` (struct_time)
