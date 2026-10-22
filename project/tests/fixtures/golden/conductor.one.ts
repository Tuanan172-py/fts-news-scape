// Đợt G — 3 bài, 1 lô.
// Chạy TRỌN chương trình này trong MỘT lệnh run_code. Không tách thành nhiều bước.
const BATCHES = [{"id": "G1", "path": "<DATA_ROOT>\\G1.task.json", "n": 2, "windows": [[1, 40]]}];
const OUT = "<DATA_ROOT>\\agent_outputs_article";
const CONCURRENCY = 1;

// Ghép lại nội dung packet từ các cửa sổ dòng. Công cụ đọc trả về đối tượng
// {path, offset, lines: [{number, text}], totalLines}. Dạng chuỗi có số dòng đứng
// đầu mỗi dòng vẫn được bóc, để chương trình không vỡ khi runtime đổi định dạng.
// Không bóc được dòng nào thì ném lỗi kèm kiểu dữ liệu nhận được, thay vì trả về
// một packet rỗng không nói lên nguyên nhân.
async function readPacket(b) {
  let text = "";
  for (const [offset, limit] of b.windows) {
    const r = await tools.read({ file_path: b.path, offset, limit });
    if (Array.isArray(r?.lines)) {
      for (const l of r.lines) text += (typeof l === "string" ? l : (l?.text ?? "")) + "\n";
      continue;
    }
    const body = typeof r === "string" ? r : (r?.content ?? r?.text ?? "");
    let matched = 0;
    for (const line of String(body).split("\n")) {
      const m = line.match(/^\s*(\d+): ?(.*)$/);
      if (m) { text += m[2] + "\n"; matched++; }
    }
    if (!matched) {
      const keys = r && typeof r === "object" ? Object.keys(r).join(",") : "-";
      throw new Error(`đọc ${b.id} tại dòng ${offset}: nhận ${typeof r} [${keys}], không bóc được dòng nào`);
    }
  }
  if (!text.trim()) throw new Error(`đọc ${b.id}: ghép xong vẫn rỗng`);
  return text;
}

// Đọc trọn mọi packet TRƯỚC khi gọi mô hình. Đọc hỏng thì dừng cả đợt khi chưa tiêu
// token nào; trước đây lỗi đọc chỉ lộ ra sau khi lượt hâm cache đã chạy.
const PACKETS = {};
const readFailed = [];
for (const b of BATCHES) {
  try { PACKETS[b.id] = await readPacket(b); }
  catch (e) { readFailed.push({ id: b.id, why: String(e?.message ?? e) }); }
}
if (readFailed.length) {
  return { wave: "G", batches: 0, failed: readFailed,
           stopped: "đọc packet hỏng, chưa gọi mô hình" };
}

async function runBatch(b) {
  const packet = PACKETS[b.id];
  const res = await tools.agent_article({
    description: "article " + b.id,
    prompt: packet
  });
  // Công cụ gọi agent trả về {kind, runId, output:[{type:"text", text}]}. Ghi thẳng
  // đối tượng ấy ra đĩa thì tệp mang lớp vỏ, và bộ bung bản ghi đọc nhầm lớp vỏ
  // thành một bản ghi rác — đúng thứ đã xảy ra với các tệp _cNN của W1 và W2.
  const parts = Array.isArray(res?.output)
    ? res.output.filter(o => o?.type === "text").map(o => o.text).join("")
    : "";
  const text = typeof res === "string" ? res
             : (parts || res?.text || res?.content || JSON.stringify(res));
  await tools.write({ file_path: OUT + "\\" + b.id + ".output.json", content: text });
  return { id: b.id, ok: true, chars: text.length };
}

const done = [];
for (let i = 0; i < BATCHES.length; i += CONCURRENCY) {
  const slice = BATCHES.slice(i, i + CONCURRENCY);
  // Một lô ném lỗi không được kéo đổ cả `Promise.all`: các lô khác đã ghi xong đầu
  // ra, và người vận hành cần biết đúng lô nào hỏng vì sao.
  done.push(...await Promise.all(slice.map(b => runBatch(b).catch(e => (
    { id: b.id, ok: false, why: String(e?.message ?? e).slice(0, 200) })))));
}

// Chỉ trả về con số. Nội dung packet và đầu ra của lô KHÔNG được vào ngữ cảnh.
return { wave: "G", batches: done.length,
         failed: done.filter(d => !d.ok).map(d => ({ id: d.id, why: d.why })) };
