// 화면이 그려지기 전에 테마 적용 (깜빡임 방지): 저장된 값 → 없으면 OS 설정
// index.html 안에 직접 쓰지 않고 파일로 둠 — 서버의 보안 정책(CSP)이 페이지 안 스크립트를 막기 때문 (deploy/Caddyfile)
(function () {
  var t = null;
  try { t = localStorage.getItem("theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  document.documentElement.dataset.theme = t;
})();
