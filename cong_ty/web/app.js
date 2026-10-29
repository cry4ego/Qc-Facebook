// Tab "Công ty AI" (chi phí 0đ): họp sáng + duyệt đề xuất, báo cáo sáng bằng code, ghi kết quả khách, tình trạng sổ sự thật.
// Dùng $, esc, num của web/index.html. Mọi chữ lấy từ máy chủ (kể cả chữ do AI viết) đều qua esc() trước khi chèn vào trang.
const CT_NGAY_KHACH = 30;
const CT_TRANG_THAI = {giam: ["bad", "Đang giảm"], on_dinh: ["ok", "Ổn định"], thieu_so_lieu: ["", "Chưa đủ số liệu"]};
const CT_VAI = {giam_doc: "Giám đốc", phan_tich: "Phân tích", noi_dung: "Nội dung", san_khach: "Săn khách",
                cham_soc_khach: "Chăm sóc khách", rui_ro: "Kiểm soát rủi ro"};
const CT_TT_DE_XUAT = {cho_duyet: ["warn", "Chờ bạn duyệt"], da_duyet: ["ok", "Bạn đã duyệt"], tu_choi: ["", "Bạn từ chối"],
                       da_lam: ["ok", "Đã làm"], dang_lam: ["warn", "Đang làm"], hoan: ["", "Hoãn"], bi_chan: ["bad", "Bị chặn"]};
const CT_CHO_TU_DONG_MS = 15000;      // đang họp: làm mới khối họp mỗi ... mili giây
const CT_TOI_DA_LAN_HOI = 120;        // ... nhưng chỉ tối đa ngần ấy lần (15 giây x 120 = 30 phút) rồi thôi
let ctFlash = "";
let ctThongBaoHop = "";
let ctBound = false;
let ctHen = null;
let ctLanHoi = 0;

const ctDM = d => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : "");
const ctTien = n => (n ? `${Number(n).toLocaleString("vi-VN")}đ` : "");
const ctHomNay = () => new Date().toLocaleDateString("sv");   // YYYY-MM-DD theo giờ máy

async function ctJSON(url, options) {
  const r = await fetch(url, options);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Lỗi ${r.status}`);
  return j;
}
const ctGuiJSON = (url, obj) => ctJSON(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(obj)});

const ctBang = (tieuDe, dong) => `<div class="table-wrap"><table><thead><tr>${tieuDe.map(t => `<th>${t}</th>`).join("")}</tr></thead>
  <tbody>${dong}</tbody></table></div>`;

// ---------- họp sáng + đề xuất ----------
function ctHop(h) {
  const cd = h.che_do, gan = h.gan_nhat && h.gan_nhat.cuoc_hop;
  const nguonAI = h.ai.length ? h.ai.map(a => `${esc(a.nguon)} ${a.so_luot}/${a.tran}${a.het ? " (hết lượt)" : ""}`).join(" · ")
    : "chưa có nguồn AI nào (công ty họp bằng luật)";
  const tomTat = gan
    ? `<p><b>Họp sáng ${esc(gan.ngay)}</b> (${esc(gan.trang_thai === "xong" ? "xong" : gan.trang_thai)}${gan.nguon_ai ? " · AI: " + esc(gan.nguon_ai) : " · không dùng AI"}):
        ${esc(gan.tom_tat)}${gan.loi ? ` <span class="err">${esc(gan.loi)}</span>` : ""}</p>`
    : `<p class="muted">Chưa có cuộc họp nào. Bấm "Họp ngay", hoặc để cửa sổ "QC-Facebook Hop" tự họp lúc ${h.gio_hop}h sáng.</p>`;
  const tl = h.tu_lam;
  const ghiChuChe = !cd.xong
    ? `Chế độ quan sát — ngày ${cd.ngay}/${cd.tong}: công ty chỉ họp và đề xuất, mọi việc đều do bạn duyệt. Việc nhỏ (tắt mẫu bình luận
       hay bị chặn, thêm mẫu bình luận do AI viết) có nút "Đồng ý và làm luôn"; công tắc tự làm mở khóa sau ${cd.tong} ngày quan sát.`
    : tl.bat
      ? `Công ty đang được tự làm các việc nhỏ trong giới hạn: tắt mẫu bình luận hay bị chặn (tối đa 5 mẫu mỗi ngày, luôn còn ít nhất
         10 mẫu) và thêm mẫu bình luận do AI viết (tối đa 3 mẫu mỗi ngày, 9 mẫu AI đang bật; giá, SĐT, địa chỉ do code ghép). Mọi việc
         hoàn tác được ở mục "Việc công ty đã làm"; việc khác vẫn do bạn duyệt.`
      : "Đã hết thời gian quan sát. Công ty vẫn chỉ đề xuất; bật công tắc bên dưới nếu muốn công ty tự làm các việc nhỏ trong giới hạn.";
  const congTac = `<label class="muted" style="display:block;margin:6px 0"><input type="checkbox" id="ct-tu-lam"${tl.bat ? " checked" : ""}${cd.xong || tl.bat ? "" : " disabled"}>
    Cho công ty tự làm các việc nhỏ trong giới hạn${cd.xong ? "" : " (đang khóa)"}</label>`;
  return `<h2 style="margin-top:0">Công ty AI họp sáng</h2>
    <div class="note ${cd.xong ? "ok" : "warn"}">${ghiChuChe}</div>${congTac}
    ${ctThongBaoHop ? `<div class="note ok">${esc(ctThongBaoHop)}</div>` : ""}${tomTat}
    <div class="toolbar"><button class="primary" id="ct-hop-ngay"${h.dang_cho_hop ? " disabled" : ""}>${h.dang_cho_hop ? "Đang chờ họp…" : "Họp ngay"}</button>
      <span class="muted">Lượt AI hôm nay: ${nguonAI}. Họp cần cửa sổ "QC-Facebook Hop" đang chạy (có trong chay-ngam.bat).</span></div>`;
}

function ctTheDeXuat(d, nut) {
  return `<div class="pcard" style="margin-bottom:10px"><div class="pbody">
    <div class="phead"><span class="pname">${esc(d.tieu_de)}</span>
      <span class="b info">${esc(CT_VAI[d.vai] || d.vai)} · ${esc(CT_NGUON[d.nguon] || "AI")}</span></div>
    <div class="ctext">${esc(d.noi_dung)}</div>
    <div class="muted"><b>Vì sao:</b> ${esc(d.vi_sao)}</div>
    ${d.ky_vong ? `<div class="muted"><b>Kỳ vọng:</b> ${esc(d.ky_vong)}</div>` : ""}
    ${d.rui_ro ? `<div class="muted"><b>Rủi ro:</b> ${esc(d.rui_ro)}</div>` : ""}
    <div class="muted">Đo kết quả vào ${esc(d.ngay_do)}</div>
    <div class="pactions">${nut}</div></div></div>`;
}

// Đề xuất do LUẬT gắn việc có cấu trúc (tham_so) thì công ty làm luôn được; chữ do AI viết thì bạn tự làm tay
const ctLamLuonDuoc = d => ["luat", "mau_ai", "tu_khoa_ai"].includes(d.nguon) && !!d.tham_so;
const CT_NGUON = {luat: "theo luật", mau_ai: "AI viết · code kiểm tra", tu_khoa_ai: "AI đề xuất · code kiểm tra"};
const ctNutLamLuon = (d, nhan) => (ctLamLuonDuoc(d)
  ? `<button class="primary" data-ct-quyet="lam_luon" data-id="${esc(d.id)}">${nhan}</button>` : "");

function ctDeXuat(h) {
  const nutDuyet = d => `<input type="text" id="ct-gc-${esc(d.id)}" placeholder="Ghi chú (không bắt buộc)" maxlength="500" style="flex:1">
    ${ctNutLamLuon(d, "Đồng ý và làm luôn")}
    <button class="${ctLamLuonDuoc(d) ? "" : "primary"}" data-ct-quyet="da_duyet" data-id="${esc(d.id)}">${ctLamLuonDuoc(d) ? "Đồng ý (tôi tự làm)" : "Đồng ý"}</button>
    <button class="danger" data-ct-quyet="tu_choi" data-id="${esc(d.id)}">Từ chối</button>`;
  const choDuyet = h.cho_duyet.length
    ? `<h2>Đề xuất chờ bạn duyệt (${h.cho_duyet.length})</h2>${h.cho_duyet.map(d => ctTheDeXuat(d, nutDuyet(d))).join("")}`
    : `<h2>Đề xuất chờ bạn duyệt</h2><p class="muted">Không có đề xuất nào đang chờ.</p>`;
  const daDuyet = h.lich_su.filter(d => d.trang_thai === "da_duyet");
  const nutLam = d => `${ctNutLamLuon(d, "Công ty làm luôn")}
    <button class="primary" data-ct-quyet="da_lam" data-id="${esc(d.id)}">Tôi đã làm xong</button>`;
  return choDuyet + (daDuyet.length
    ? `<h2>Bạn đã duyệt — làm xong thì bấm "Tôi đã làm xong"</h2>${daDuyet.map(d => ctTheDeXuat(d, nutLam(d))).join("")}` : "");
}

const CT_VIEC = {tat_mau: "Tắt mẫu bình luận", them_mau: "Thêm mẫu bình luận do AI viết", them_tu_khoa: "Thêm từ khóa tìm nhóm"};

function ctViecDaLam(h) {
  if (!h.viec_da_lam.length) return "";
  const dong = h.viec_da_lam.map(v => {
    const mau = v.tu_khoa.length ? v.tu_khoa.map(esc).join("; ") : v.variant_ids.map(i => `#${esc(i)}`).join(", ");
    const tinhTrang = v.hoan_tac_luc ? `<span class="b">Đã hoàn tác ${esc(v.hoan_tac_luc.slice(0, 16))}</span>`
      : `<button data-ct-hoantac="${esc(v.id)}">Hoàn tác</button>`;
    const chuAI = v.mo_ta.length ? `<div class="muted ctext">${v.mo_ta.map(m => `“${esc(m)}”`).join("<br>")}</div>` : "";
    return `<tr><td>${esc(v.luc.slice(0, 16))}</td><td>${esc(v.tieu_de)}</td>
      <td>${esc(CT_VIEC[v.hanh_dong] || v.hanh_dong)}: ${mau}${chuAI}</td><td>${tinhTrang}</td></tr>`;
  }).join("");
  return `<h2>Việc công ty đã làm</h2>${ctBang(["Lúc", "Đề xuất", "Việc", ""], dong)}`;
}

const ctKhoiHop = h => ctHop(h) + ctDeXuat(h) + ctViecDaLam(h);

function ctBienBan(h) {
  if (!h.gan_nhat) return "";
  const dong = h.gan_nhat.ban_tin.map(b => `<p><b>${esc(CT_VAI[b.vai] || b.vai)}</b> <span class="muted">(vòng ${b.vong})</span><br>
    <span class="ctext">${esc(b.noi_dung)}</span></p>`).join("");
  return `<details class="import"><summary>Biên bản cuộc họp gần nhất</summary>${dong || '<p class="muted">Trống.</p>'}</details>`;
}

function ctLichSu(h) {
  if (!h.lich_su.length) return "";
  const dong = h.lich_su.map(d => {
    const [cls, nhan] = CT_TT_DE_XUAT[d.trang_thai] || ["", d.trang_thai];
    const ghiChu = [d.ly_do, d.ghi_chu_chu_shop && `Bạn ghi: ${d.ghi_chu_chu_shop}`].filter(Boolean).join(" · ");
    return `<tr><td>${esc(d.tao_luc.slice(0, 10))}</td><td>${esc(CT_VAI[d.vai] || d.vai)}</td><td>${esc(d.tieu_de)}</td>
      <td><span class="b ${cls}">${esc(nhan)}</span></td><td>${esc(ghiChu)}</td></tr>`;
  }).join("");
  return `<h2>Lịch sử đề xuất</h2>${ctBang(["Ngày", "Vai", "Đề xuất", "Trạng thái", "Lý do / ghi chú"], dong)}`;
}

// ---------- báo cáo sáng, ghi khách, sổ sự thật ----------
function ctNotes(bc) {
  return bc.nhan_xet.map(n => `<div class="note ${n.muc === "chu_y" ? "warn" : "ok"}">${esc(n.noi_dung)}</div>`).join("");
}

function ctTiles(bc) {
  const p = bc.pheu, k = bc.khach.tong;
  const tile = (n, nhan, cls = "") => `<div class="tile ${cls}"><div class="n">${num(n)}</div><div class="l">${nhan}</div></div>`;
  return `<div class="tiles">${tile(p.bai_thay, "Bài bot xem")}${tile(p.bai_mua, "Bài người cần mua")}
    ${tile(p.dat_loc, "Đạt mọi bộ lọc")}${tile(p.bai_binh_luan, "Bài đã bình luận", "ok")}
    ${tile(k.goi + k.nhan + k.mua, "Khách (gọi · nhắn · mua)", "ok")}</div>`;
}

function ctNgay(bc) {
  const dong = bc.chuoi.slice().reverse().map(d => `<tr><td>${ctDM(d.ngay)}${d.chua_het ? ' <span class="b">chưa hết ngày</span>' : ""}</td>
    <td>${num(d.quet)}</td><td>${num(d.bai_thay)}</td><td>${num(d.bai_mua)}</td><td>${num(d.dat_loc)}</td>
    <td>${num(d.bai_binh_luan)}</td><td>${num(d.binh_luan_gui)}</td><td>${d.goi} / ${d.nhan} / ${d.mua}</td></tr>`).join("");
  return `<h2>Theo ngày</h2>${ctBang(["Ngày", "Lần quét", "Bài thấy", "Bài MUA", "Đạt lọc", "Bài đã BL", "Bình luận",
    "Gọi / nhắn / mua"], dong)}`;
}

function ctForm(bc, kh) {
  const ten = [...new Set([...bc.nhom.map(r => r.ten), ...Object.keys(kh.nguon)])].filter(t => t && t !== "Không rõ");
  const homNay = ctHomNay();
  return `<h2>Ghi kết quả khách</h2>
  <p class="muted" style="margin-top:0">Mỗi tối ghi vài số: hôm nay có bao nhiêu khách gọi, nhắn, mua. Biết khách thấy shop ở nhóm
    nào thì điền tên nhóm vào ô Nguồn — công ty AI dùng số này để biết nhóm nào ra khách.</p>
  <div class="filters">
    <input type="date" id="ct-ngay" value="${homNay}" max="${homNay}" title="Ngày khách liên hệ">
    <select id="ct-loai"><option>Gọi</option><option>Nhắn</option><option>Mua</option></select>
    <input type="number" id="ct-sl" value="1" min="1" max="500" style="width:80px" title="Số lượng">
    <input type="search" id="ct-nguon" list="ct-nguon-ds" maxlength="200" placeholder="Nguồn: tên nhóm (để trống nếu chưa rõ)">
    <datalist id="ct-nguon-ds">${ten.map(t => `<option value="${esc(t)}"></option>`).join("")}</datalist>
    <input type="text" id="ct-tien" inputmode="numeric" placeholder="Số tiền (nếu mua)" style="width:150px">
    <input type="text" id="ct-ghichu" maxlength="500" placeholder="Ghi chú">
    <button class="primary" id="ct-them">Ghi</button>
    <span id="ct-msg" class="okmsg">${esc(ctFlash)}</span>
  </div>`;
}

function ctKhach(kh) {
  if (!kh.rows.length) return `<p class="muted">Chưa ghi lượt khách nào trong ${CT_NGAY_KHACH} ngày qua.</p>`;
  const dong = kh.rows.slice(0, 30).map(r => `<tr><td>${ctDM(r.ngay)}</td><td>${esc(r.loai)}</td><td>${r.so_luong}</td>
    <td>${esc(r.nguon) || '<span class="muted">Không rõ</span>'}</td><td>${ctTien(r.so_tien)}</td><td>${esc(r.ghi_chu)}</td>
    <td class="gact"><button class="danger" data-ct-xoa="${esc(r.id)}">Xóa</button></td></tr>`).join("");
  return ctBang(["Ngày", "Loại", "Số lượng", "Nguồn", "Tiền", "Ghi chú", ""], dong);
}

function ctSuThat(st) {
  const dien = st.so_truong - st.chua_dien.length;
  const thieu = st.chua_dien.length ? ` Còn thiếu: ${esc(st.chua_dien.join(", "))}.` : "";
  return `<h2>Sổ sự thật</h2><div class="note ${st.chua_dien.length || st.loi ? "warn" : "ok"}">
    ${st.loi ? esc(st.loi) : `Đã điền ${dien}/${st.so_truong} mục.${thieu}`} Mở file <code>${esc(st.duong_dan)}</code> bằng Notepad
    để điền, lưu lại là xong (không cần khởi động lại). Công ty AI chỉ được nói những gì có trong sổ này và tab Sản phẩm.</div>`;
}

function ctNhom(bc) {
  if (!bc.nhom.length) return "";
  const dong = bc.nhom.map(r => `<tr><td>${esc(r.ten)}</td><td>${num(r.quet)}</td><td>${num(r.mua)}</td><td>${num(r.dat_loc)}</td>
    <td>${num(r.bai_binh_luan)}</td><td>${num(r.khach)}</td></tr>`).join("");
  return `<h2>Nhóm nổi bật trong ${bc.so_ngay} ngày</h2>${ctBang(["Nhóm", "Lần quét", "Bài MUA", "Đạt lọc", "Bài đã BL", "Khách"], dong)}`;
}

function ctBoQua(bc) {
  if (!bc.ly_do_bo_qua.length) return "";
  const dong = bc.ly_do_bo_qua.map(r => `<tr><td>${esc(r.ly_do)}</td><td>${num(r.so_bai)}</td></tr>`).join("");
  return `<h2>Bài người cần mua bị bỏ qua vì</h2>${ctBang(["Lý do", "Số bài"], dong)}`;
}

function ctMau(bc) {
  const m = bc.mau;
  if (!m.so_mau_lech) return `<h2>Mẫu bình luận</h2><p class="muted">Đã soát ${m.so_mau} mẫu đang bật theo tab Sản phẩm và sổ sự thật: không thấy lệch.</p>`;
  const gia = m.gia_la.map(g => `${num(g.gia)}đ (${g.so_mau} mẫu)`).join(", ");
  const dong = m.van_de.map(v => `<tr><td>#${v.id}</td><td>${esc(v.san_pham)}</td><td>${v.van_de.map(esc).join("<br>")}</td></tr>`).join("");
  return `<h2>Mẫu bình luận lệch sổ sự thật</h2>
    <p class="muted" style="margin-top:0">${m.so_mau_lech}/${m.so_mau} mẫu đang bật có thông tin không khớp tab Sản phẩm hoặc sổ sự thật.
    ${gia ? `Giá chưa có trong bảng Sản phẩm: ${esc(gia)}. Đúng thì thêm vào mục "Giá được phép nhắc thêm" của sổ sự thật; sai thì sửa mẫu.` : ""}</p>
    ${ctBang(["Mẫu", "Sản phẩm", "Vấn đề"], dong)}`;
}

function ctPage(bc, kh, st, ngay, h) {
  const [cls, nhan] = CT_TRANG_THAI[bc.chan_doan.trang_thai] || ["", ""];
  return `<div id="ct-hop-khoi">${ctKhoiHop(h)}</div>
    <div class="toolbar" style="margin-top:24px"><h2 style="margin:0">Báo cáo sáng</h2>
    <input type="date" id="ct-ngay-bc" value="${esc(ngay)}" max="${ctHomNay()}" title="Xem báo cáo của ngày khác">
    <span class="muted">Tính bằng code từ dữ liệu của bot, không tốn lượt AI · ${esc(bc.pheu.tu)} → ${esc(bc.pheu.den)}</span></div>
    ${ctNotes(bc)}${ctTiles(bc)}
    <h2>Chẩn đoán số bài <span class="b ${cls}">${nhan}</span></h2>
    <ul>${bc.chan_doan.cau.map(c => `<li>${esc(c)}</li>`).join("")}</ul>
    ${ctNgay(bc)}${ctForm(bc, kh)}${ctKhach(kh)}${ctSuThat(st)}${ctNhom(bc)}${ctBoQua(bc)}${ctMau(bc)}
    ${ctLichSu(h)}${ctBienBan(h)}
    <details class="import"><summary>Bản chữ của báo cáo</summary><pre class="ctext">${esc(bc.van_ban)}</pre></details>`;
}

// ---------- thao tác ----------
async function ctThem() {
  const g = id => $(id).value.trim();
  const msg = $("#ct-msg");
  msg.className = "err";
  msg.textContent = "";
  try {
    await ctGuiJSON("/api/congty/khach", {ngay: g("#ct-ngay"), loai: g("#ct-loai"), so_luong: g("#ct-sl") || 1,
                                          nguon: g("#ct-nguon"), so_tien: g("#ct-tien"), ghi_chu: g("#ct-ghichu")});
    ctFlash = "Đã ghi.";
    await loadCongTy();
  } catch (e) {
    msg.textContent = e.message;
  }
}

async function ctHopNgay() {
  try {
    await ctJSON("/api/congty/hop", {method: "POST"});
    ctThongBaoHop = 'Đã yêu cầu họp — cửa sổ "QC-Facebook Hop" sẽ họp trong vòng một phút, trang này tự cập nhật.';
    await loadCongTy();
  } catch (e) {
    alert(e.message);
  }
}

async function ctQuyet(id, quyet) {
  if (quyet === "lam_luon" && !confirm("Công ty sẽ làm việc này ngay bây giờ (tắt mẫu hoặc thêm mẫu bình luận mới — hoàn tác được "
                                        + "ở mục Việc công ty đã làm). Làm luôn?")) return;
  const gc = $(`#ct-gc-${id}`);
  try {
    await ctGuiJSON(`/api/congty/dexuat/${id}`, {quyet_dinh: quyet, ghi_chu: gc ? gc.value.trim() : ""});
    ctThongBaoHop = quyet === "lam_luon" ? 'Công ty đã làm xong — xem mục "Việc công ty đã làm" (có nút Hoàn tác).'
      : "Đã ghi quyết định của bạn.";
    await loadCongTy();
  } catch (e) {
    alert(e.message);
  }
}

async function ctHoanTac(id) {
  if (!confirm("Hoàn tác việc này? (Mẫu đã tắt thì bật lại, mẫu đã thêm thì tắt đi, từ khóa đã thêm thì bỏ đi.)")) return;
  try {
    await ctJSON(`/api/congty/nhatky/${id}/hoantac`, {method: "POST"});
    ctThongBaoHop = "Đã hoàn tác — mọi thứ về như trước khi công ty làm việc này.";
    await loadCongTy();
  } catch (e) {
    alert(e.message);
  }
}

async function ctTuLam(bat) {
  try {
    await ctGuiJSON("/api/congty/tulam", {bat});
    ctThongBaoHop = bat ? "Đã bật: từ cuộc họp sau, công ty tự làm các việc nhỏ trong giới hạn." : "Đã tắt công tắc tự làm.";
  } catch (e) {
    alert(e.message);
  }
  await loadCongTy();     // vẽ lại để công tắc khớp với trạng thái thật trên máy chủ
}

function ctBind() {
  if (ctBound) return;
  ctBound = true;
  const root = $("#ct-root");
  root.addEventListener("click", async e => {
    if (e.target.id === "ct-them") return ctThem();
    if (e.target.id === "ct-hop-ngay") return ctHopNgay();
    if (e.target.dataset.ctQuyet) return ctQuyet(e.target.dataset.id, e.target.dataset.ctQuyet);
    if (e.target.dataset.ctHoantac) return ctHoanTac(e.target.dataset.ctHoantac);
    const id = e.target.dataset.ctXoa;
    if (!id || !confirm("Xóa dòng khách này?")) return;
    try {
      await ctJSON(`/api/congty/khach/${id}`, {method: "DELETE"});
      ctFlash = "Đã xóa.";
      await loadCongTy();
    } catch (err) {
      alert(err.message);
    }
  });
  root.addEventListener("change", e => {
    if (e.target.id === "ct-ngay-bc") loadCongTy();
    if (e.target.id === "ct-tu-lam") ctTuLam(e.target.checked);
  });
}

const ctDangHop = h => h.dang_cho_hop || (h.gan_nhat && h.gan_nhat.cuoc_hop.trang_thai === "dang_hop");

// Đang họp (hoặc đang chờ cửa sổ họp): chỉ làm mới KHỐI HỌP + ĐỀ XUẤT, không vẽ lại cả tab (đỡ mất chữ bạn đang gõ ở form
// ghi khách), và bỏ cuộc sau CT_TOI_DA_LAN_HOI lần (30 phút) để cuộc họp kẹt không làm trang gọi máy chủ mãi.
function ctHenLamMoiHop(h) {
  clearTimeout(ctHen);
  if (!ctDangHop(h) || ctLanHoi >= CT_TOI_DA_LAN_HOI) return;
  ctHen = setTimeout(async () => {
    if ($("#tab-congty").hidden) return;
    ctLanHoi += 1;
    let moi = h;
    try {
      moi = await ctJSON("/api/congty/hop");
      $("#ct-hop-khoi").innerHTML = ctKhoiHop(moi);
    } catch (e) {
      // máy chủ tạm thời không trả lời: giữ nguyên màn hình, lần sau thử lại
    }
    ctHenLamMoiHop(moi);
  }, CT_CHO_TU_DONG_MS);
}

async function loadCongTy() {
  ctBind();
  clearTimeout(ctHen);
  const root = $("#ct-root");
  const ngay = ($("#ct-ngay-bc") || {}).value || ctHomNay();
  try {
    const [bc, kh, st, h] = await Promise.all([
      ctJSON(`/api/congty/baocao?date=${encodeURIComponent(ngay)}`),
      ctJSON(`/api/congty/khach?days=${CT_NGAY_KHACH}`),
      ctJSON("/api/congty/suthat"),
      ctJSON("/api/congty/hop")]);
    root.innerHTML = ctPage(bc, kh, st, ngay, h);
    ctLanHoi = 0;
    ctHenLamMoiHop(h);
  } catch (e) {
    root.innerHTML = `<div class="note bad">Không tải được tab Công ty AI: ${esc(e.message)}</div>`;
  }
  ctFlash = "";
  ctThongBaoHop = "";
}

if (!$("#tab-congty").hidden) loadCongTy();   // mở thẳng vào #congty
