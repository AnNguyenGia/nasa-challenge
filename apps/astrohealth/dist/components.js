'use strict';
window.UI = {
  escape(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },
  panel(title, body) {
    return `<section class="panel"><div class="panel-title">${this.escape(title)}</div>${body}</section>`;
  },
  value(label, value, unit, source, stale) {
    return `<div class="value-tile"><div><label>${this.escape(label)}</label><small>${this.escape(source)}${stale ? ' / STALE' : ''}</small></div><div class="value">${this.escape(value)}<small>${this.escape(unit)}</small></div></div>`;
  },
  bodyMap(selected) {
    const zones = [
      ['neuro', '01 THẦN KINH / NEURO', 50, 12],
      ['resp', '02 HÔ HẤP / RESP', 38, 30],
      ['cardio', '03 TIM MẠCH / CARDIO', 54, 27],
      ['immune', '04 MIỄN DỊCH / IMMUNE', 49, 41],
      ['musculoskeletal', '05 CƠ XƯƠNG / MSK', 40, 62]
    ];
    return `<div class="body-map unity-viewport" id="body-map-viewport">
      <div class="viewport-hud-header">
        <span class="hud-tag">SCENE: MAN</span>
        <div class="hud-tools">
          <span class="hud-tool-btn active">3D</span>
          <button type="button" class="model-expand-control" data-action="body-zoom" aria-label="Mở rộng hoặc thu nhỏ mô hình 3D" aria-pressed="false" title="Mở rộng hoặc thu nhỏ mô hình 3D">⤢</button>
        </div>
        <span class="hud-coord">LOCAL / 8811</span>
      </div>
      <div class="hologram-stage" id="hologram-stage">
        <div class="man-model-stage" id="body-model-stage">
          <canvas class="man-model-canvas" id="man-model-canvas" aria-label="Mô hình người 3D Man của mattmerk; kéo để xoay, nhấp đúp để đặt lại góc nhìn"></canvas>
          <div class="model-loading" id="model-loading" role="status">ĐANG NẠP MÔ HÌNH 3D CỤC BỘ…</div>
          <img class="model-fallback" src="assets/human-hologram.png" alt="Ảnh cơ thể dự phòng khi không thể mở mô hình 3D" hidden>
          ${zones.map(([id, label, x, y]) => `
            <button type="button" class="body-hotspot ${selected === id ? 'selected' : ''}" style="left:${x}%;top:${y}%" data-organ="${id}" aria-label="Chọn ${this.escape(label)}" aria-pressed="${selected === id}" title="${this.escape(label)}">
              <span class="glow-dot" aria-hidden="true"></span>
              ${selected === id ? `<span class="hotspot-callout">${this.escape(label)} / ĐANG CHỌN</span>` : ''}
            </button>
          `).join('')}
        </div>
      </div>
      <div class="viewport-hud-footer">
        <span class="hologram-hud-hint" id="body-view-hint">KÉO ĐỂ XOAY · NHẤP ĐÚP ĐỂ ĐẶT LẠI</span>
        <button class="model-credit" type="button" data-action="model-credit" title="Tác giả và giấy phép mô hình">MAN © mattmerk · CC BY-SA 3.0</button>
      </div>
    </div>`;
  }
};
