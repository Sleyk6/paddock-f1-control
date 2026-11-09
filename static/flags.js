"use strict";
/* Simplified national flags (hand-drawn SVG, 3:2) for the F1 calendar countries.
   Simplified on purpose: correct colours and layout, without fine emblem detail.
   Unknown countries fall back to a two-letter tag. */
(function () {
  const H = (...c) => c.map((col, i) => `<rect x="0" y="${(20 / c.length) * i}" width="30" height="${20 / c.length + 0.05}" fill="${col}"/>`).join("");
  const V = (...c) => c.map((col, i) => `<rect x="${(30 / c.length) * i}" y="0" width="${30 / c.length + 0.05}" height="20" fill="${col}"/>`).join("");
  const star = (cx, cy, r, fill) => {
    let p = "";
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.42 : r;
      p += `${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)} `;
    }
    return `<polygon points="${p}" fill="${fill}"/>`;
  };
  const union = (w, h) => `<svg x="0" y="0" width="${w}" height="${h}" viewBox="0 0 60 30" preserveAspectRatio="none"><rect width="60" height="30" fill="#012169"/><path d="M0,0 60,30 M60,0 0,30" stroke="#fff" stroke-width="6"/><path d="M0,0 60,30 M60,0 0,30" stroke="#C8102E" stroke-width="2"/><path d="M30,0V30M0,15H60" stroke="#fff" stroke-width="10"/><path d="M30,0V30M0,15H60" stroke="#C8102E" stroke-width="6"/></svg>`;
  const zig = (light, dark, x) => {
    let p = `0,0 ${x},0 `;
    for (let i = 0; i < 9; i++) p += `${x + 4},${(i + 0.5) * (20 / 9)} ${x},${(i + 1) * (20 / 9)} `;
    return `<rect width="30" height="20" fill="${dark}"/><polygon points="${p}0,20" fill="${light}"/>`;
  };
  const F = {
    AUSTRIA: H("#C8102E", "#fff", "#C8102E"),
    BELGIUM: V("#000", "#FDDA24", "#EF3340"),
    HUNGARY: H("#CE2939", "#fff", "#477050"),
    NETHERLANDS: H("#AE1C28", "#fff", "#21468B"),
    ITALY: V("#009246", "#fff", "#CE2B37"),
    MEXICO: V("#006847", "#fff", "#CE1126") + `<circle cx="15" cy="10" r="2.6" fill="#8C5A2B"/>`,
    MONACO: H("#CE1126", "#fff"),
    SPAIN: `<rect width="30" height="20" fill="#AA151B"/><rect y="5" width="30" height="10" fill="#F1BF00"/>`,
    AZERBAIJAN: H("#0092BC", "#E4002B", "#00AF66") + `<circle cx="14" cy="10" r="2.6" fill="#fff"/><circle cx="14.9" cy="10" r="2.1" fill="#E4002B"/>` + star(17.6, 10, 1.4, "#fff"),
    UAE: H("#00732F", "#fff", "#000") + `<rect width="8" height="20" fill="#FF0000"/>`,
    BAHRAIN: zig("#fff", "#CE1126", 7),
    QATAR: zig("#fff", "#8A1538", 9),
    JAPAN: `<rect width="30" height="20" fill="#fff"/><circle cx="15" cy="10" r="6" fill="#BC002D"/>`,
    CHINA: `<rect width="30" height="20" fill="#EE1C25"/>` + star(5.5, 5, 3, "#FFFF00") + star(10, 2, 1, "#FFFF00") + star(12, 4, 1, "#FFFF00") + star(12, 7, 1, "#FFFF00") + star(10, 9, 1, "#FFFF00"),
    CANADA: V("#D80621", "#fff", "#fff", "#D80621") + `<polygon points="15,4 16.2,6.6 18.2,6 17.3,9.4 19,9 17.6,11.6 15.5,11.2 15.5,14.5 14.5,14.5 14.5,11.2 12.4,11.6 11,9 12.7,9.4 11.8,6 13.8,6.6" fill="#D80621"/>`,
    USA: Array.from({ length: 13 }, (_, i) => `<rect y="${(20 / 13) * i}" width="30" height="${20 / 13 + 0.05}" fill="${i % 2 ? "#fff" : "#B22234"}"/>`).join("") + `<rect width="12" height="${(20 / 13) * 7}" fill="#3C3B6E"/>`,
    UK: union(30, 20),
    AUSTRALIA: `<rect width="30" height="20" fill="#012169"/>` + union(15, 10) + star(7.5, 15, 2.2, "#fff") + star(23, 5, 1.1, "#fff") + star(20, 9.5, 1.1, "#fff") + star(25.5, 9, 1.1, "#fff") + star(23, 16, 1.2, "#fff"),
    BRAZIL: `<rect width="30" height="20" fill="#009C3B"/><polygon points="15,2.5 27.5,10 15,17.5 2.5,10" fill="#FFDF00"/><circle cx="15" cy="10" r="4.2" fill="#002776"/>`,
    "SAUDI ARABIA": `<rect width="30" height="20" fill="#006C35"/><rect x="7" y="8" width="16" height="1.6" fill="#fff"/><rect x="8" y="13" width="14" height="1" fill="#fff"/>`,
    SINGAPORE: H("#EF3340", "#fff") + `<circle cx="7" cy="5" r="3" fill="#fff"/><circle cx="8.2" cy="5" r="2.6" fill="#EF3340"/>` + star(10.5, 3.5, 0.7, "#fff") + star(12, 5, 0.7, "#fff") + star(10.5, 6.5, 0.7, "#fff"),
    PORTUGAL: `<rect width="30" height="20" fill="#DA291C"/><rect width="12" height="20" fill="#046A38"/><circle cx="12" cy="10" r="3" fill="#FFE900"/>`,
    FRANCE: V("#002395", "#fff", "#ED2939"),
    GERMANY: H("#000", "#DD0000", "#FFCE00"),
    RUSSIA: H("#fff", "#0039A6", "#D52B1E"),
    THAILAND: `<rect width="30" height="20" fill="#A51931"/><rect y="3.33" width="30" height="13.34" fill="#F4F5F8"/><rect y="6.67" width="30" height="6.66" fill="#2D2A4A"/>`,
    DENMARK: `<rect width="30" height="20" fill="#C8102E"/><rect x="9" width="3" height="20" fill="#fff"/><rect y="8.5" width="30" height="3" fill="#fff"/>`,
    FINLAND: `<rect width="30" height="20" fill="#fff"/><rect x="8.5" width="4.5" height="20" fill="#002F6C"/><rect y="7.75" width="30" height="4.5" fill="#002F6C"/>`,
    SWEDEN: `<rect width="30" height="20" fill="#006AA7"/><rect x="9" width="3.5" height="20" fill="#FECC02"/><rect y="8.25" width="30" height="3.5" fill="#FECC02"/>`,
    NORWAY: `<rect width="30" height="20" fill="#BA0C2F"/><rect x="8" width="5" height="20" fill="#fff"/><rect y="7.5" width="30" height="5" fill="#fff"/><rect x="9.25" width="2.5" height="20" fill="#00205B"/><rect y="8.75" width="30" height="2.5" fill="#00205B"/>`,
    SWITZERLAND: `<rect width="30" height="20" fill="#DA291C"/><rect x="13.5" y="4" width="3" height="12" fill="#fff"/><rect x="9" y="8.5" width="12" height="3" fill="#fff"/>`,
    POLAND: H("#fff", "#DC143C"),
    "NEW ZEALAND": `<rect width="30" height="20" fill="#012169"/>` + union(15, 10) + star(22, 5, 1.3, "#C8102E") + star(25, 9, 1.3, "#C8102E") + star(19.5, 10, 1.1, "#C8102E") + star(22, 15.5, 1.4, "#C8102E"),
    ARGENTINA: H("#74ACDF", "#fff", "#74ACDF") + `<circle cx="15" cy="10" r="2" fill="#F6B40E"/>`,
    INDONESIA: H("#CE1126", "#fff"),
    INDIA: H("#FF9933", "#fff", "#138808") + `<circle cx="15" cy="10" r="2.2" fill="none" stroke="#000080" stroke-width=".6"/>`,
    IRELAND: V("#169B62", "#fff", "#FF883E"),
    "SOUTH AFRICA": `<rect width="30" height="20" fill="#fff"/><rect width="30" height="7" fill="#E03C31"/><rect y="13" width="30" height="7" fill="#001489"/><polygon points="0,0 12,10 0,20" fill="#007749"/><polygon points="0,3 8,10 0,17" fill="#000"/>`,
    TURKEY: `<rect width="30" height="20" fill="#E30A17"/><circle cx="11" cy="10" r="5" fill="#fff"/><circle cx="12.3" cy="10" r="4" fill="#E30A17"/>` + star(17, 10, 2, "#fff"),
  };
  const ALIAS = { "UNITED STATES": "USA", "UNITED KINGDOM": "UK", "GREAT BRITAIN": "UK", "UNITED ARAB EMIRATES": "UAE", "KOREA": "KOREA" };
  const DEMONYM = { BRITISH: "UK", ENGLISH: "UK", SCOTTISH: "UK", WELSH: "UK", DUTCH: "NETHERLANDS", MONEGASQUE: "MONACO",
    SPANISH: "SPAIN", MEXICAN: "MEXICO", AUSTRALIAN: "AUSTRALIA", CANADIAN: "CANADA", FRENCH: "FRANCE", GERMAN: "GERMANY",
    THAI: "THAILAND", JAPANESE: "JAPAN", CHINESE: "CHINA", DANISH: "DENMARK", FINNISH: "FINLAND", "NEW ZEALANDER": "NEW ZEALAND",
    AMERICAN: "USA", ITALIAN: "ITALY", ARGENTINE: "ARGENTINA", ARGENTINIAN: "ARGENTINA", BRAZILIAN: "BRAZIL", SWEDISH: "SWEDEN",
    NORWEGIAN: "NORWAY", SWISS: "SWITZERLAND", POLISH: "POLAND", AUSTRIAN: "AUSTRIA", BELGIAN: "BELGIUM", RUSSIAN: "RUSSIA",
    INDONESIAN: "INDONESIA", INDIAN: "INDIA", IRISH: "IRELAND", "SOUTH AFRICAN": "SOUTH AFRICA", HUNGARIAN: "HUNGARY", PORTUGUESE: "PORTUGAL" };
  window.flagForNationality = (nat, size) => window.flagSvg(DEMONYM[String(nat || "").toUpperCase()] || nat, size);
  window.flagSvg = function (country, size = 30) {
    const key = String(country || "").toUpperCase().trim();
    const k = ALIAS[key] || key;
    const body = F[k];
    const h = Math.round((size * 2) / 3);
    if (!body) {
      const tag = k.replace(/[^A-Z]/g, "").slice(0, 2) || "??";
      return `<svg class="flag" width="${size}" height="${h}" viewBox="0 0 30 20" role="img" aria-label="${tag}"><rect width="30" height="20" fill="#18233a"/><text x="15" y="14" text-anchor="middle" fill="#e9eef7" font-size="10" font-family="monospace">${tag}</text></svg>`;
    }
    return `<svg class="flag" width="${size}" height="${h}" viewBox="0 0 30 20" role="img" aria-label="Flag of ${k.toLowerCase()}">${body}</svg>`;
  };
})();
