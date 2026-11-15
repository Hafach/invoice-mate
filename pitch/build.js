const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const md = require("react-icons/md");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require("C:/Users/hp/.claude/skills/synced/a22a5068-e2ae-43aa-83e9-a26d6e1138c4_5f95059f-a79a-419a-9c58-a4927d6fde7e/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "Invoice_Mate_Pitch.pptx";

// Cedar-ink green + paper white + receipt-highlighter amber
const HEX = {
  ink: "0B3D2E", leaf: "1F7A5A", mint: "E6F2EC", paper: "FFFFFF",
  amber: "FFB000", coral: "E4572E", text: "102A21", muted: "5B6F66",
};
const THEME = {
  name: "Invoice Mate",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: HEX.text, lt1: HEX.paper, dk2: HEX.ink, lt2: HEX.mint,
    accent1: HEX.leaf, accent2: HEX.amber, accent3: HEX.coral, accent4: "2E9E75",
    accent5: "8FBFA8", accent6: HEX.muted, hlink: HEX.leaf, folHlink: HEX.muted,
  },
};

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625
  pres.title = "Invoice Mate pitch";
  pres.author = "Invoice Mate team";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------- layouts ----------
  pres.defineSlideMaster({
    title: "DARK", background: { color: HEX.ink },
    objects: [],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { color: HEX.paper },
    margin: [0.4, 0.5, 0.4, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9, h: 0.75, fontFace: THEME.headFontFace,
          fontSize: 32, bold: true, color: C.text2, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "INVOICE MATE · ALPHAHACK 2026", options: { x: 0.5, y: 5.2, w: 5, h: 0.3, fontSize: 9, color: C.accent6, charSpacing: 2, margin: 0 } } },
    ],
    slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.3, fontSize: 9, color: C.accent6, align: "right" },
  });

  const I = {
    file: await icon(fa.FaFileInvoiceDollar, HEX.ink),
    fileW: await icon(fa.FaFileInvoiceDollar, HEX.paper),
    camera: await icon(fa.FaCamera, HEX.paper),
    brain: await icon(fa.FaMicrochip, HEX.paper),
    calc: await icon(fa.FaCalculator, HEX.paper),
    lock: await icon(fa.FaLock, HEX.ink),
    lockW: await icon(fa.FaLock, HEX.paper),
    excel: await icon(fa.FaFileExcel, HEX.paper),
    clock: await icon(fa.FaClock, HEX.paper),
    lang: await icon(fa.FaLanguage, HEX.paper),
    money: await icon(fa.FaMoneyBillWave, HEX.paper),
    copy: await icon(fa.FaCopy, HEX.paper),
    mic: await icon(fa.FaMicrophone, HEX.ink),
    cloudOff: await icon(md.MdCloudOff, HEX.paper),
    shield: await icon(fa.FaShieldAlt, HEX.paper),
    user: await icon(fa.FaUserCheck, HEX.paper),
    store: await icon(fa.FaStore, HEX.paper),
    briefcase: await icon(fa.FaBriefcase, HEX.paper),
    chip: await icon(fa.FaMicrochip, HEX.ink),
    bolt: await icon(fa.FaBolt, HEX.ink),
    pdf: await icon(fa.FaFilePdf, HEX.leaf), word: await icon(fa.FaFileWord, HEX.leaf),
    xls: await icon(fa.FaFileExcel, HEX.leaf), mail: await icon(fa.FaEnvelope, HEX.leaf),
    zip: await icon(fa.FaFileArchive, HEX.leaf), phone: await icon(fa.FaMobileAlt, HEX.leaf),
    img: await icon(fa.FaImage, HEX.leaf), cam: await icon(fa.FaCamera, HEX.leaf),
    check: await icon(fa.FaCheck, HEX.ink),
  };
  const qr = "image/png;base64," + fs.readFileSync(path.join(__dirname, "qr.png")).toString("base64");

  const T = (s, text, o) => s.addText(text, Object.assign({ isTextBox: true, margin: 0 }, o));
  const circle = (s, x, y, d, fill, img, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: name + " circle" });
    s.addImage({ data: img, x: x + d * 0.26, y: y + d * 0.26, w: d * 0.48, h: d * 0.48, altText: name, objectName: name + " icon" });
  };
  const card = (s, x, y, w, h, fill, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill }, objectName: name,
    shadow: { type: "outer", color: "0B3D2E", opacity: 0.12, blur: 8, offset: 2, angle: 90 } });

  // ---------- 1. Title ----------
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Opening" });
  // receipt illustration
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.6, y: 0.7, w: 2.6, h: 3.9, rectRadius: 0.1, fill: { color: HEX.paper }, line: { color: HEX.paper }, rotate: 6, objectName: "receipt" });
  [1.25, 1.55, 1.85, 2.15, 2.45, 2.75].forEach((yy, i) => s.addShape(pres.shapes.RECTANGLE, {
    x: 6.95 + (i % 2) * 0.05, y: yy, w: i === 5 ? 1.0 : 1.9 - (i % 3) * 0.35, h: 0.09, fill: { color: i === 5 ? HEX.amber : "D5E4DC" }, line: { type: "none" }, rotate: 6, objectName: "receipt line " + i }));
  s.addShape(pres.shapes.OVAL, { x: 7.85, y: 3.25, w: 1.1, h: 1.1, fill: { color: HEX.amber }, line: { color: HEX.amber }, objectName: "approved stamp" });
  s.addImage({ data: I.check, x: 8.12, y: 3.52, w: 0.56, h: 0.56, altText: "Approved", objectName: "stamp icon" });
  T(s, "ALPHAHACK 2026 · BYBLOS", { x: 0.6, y: 0.9, w: 5, h: 0.3, fontSize: 12, color: HEX.amber, charSpacing: 3, bold: true });
  T(s, "Invoice Mate", { x: 0.6, y: 1.35, w: 6, h: 1.1, fontFace: THEME.headFontFace, fontSize: 54, bold: true, color: HEX.paper });
  T(s, "Snap it. Check it. Approve it.\nIt's in Excel.", { x: 0.6, y: 2.55, w: 5.6, h: 1.0, fontSize: 22, color: "CFE6DA", italic: true });
  T(s, "An AI agent for supplier invoices, running 100% inside the shop", { x: 0.6, y: 4.2, w: 5.6, h: 0.4, fontSize: 14, color: "9CC3B1" });
  s.addNotes("Hook: every Lebanese shop types supplier invoices into Excel by hand. Invoice Mate does it end to end, on a small device in the shop.");

  // ---------- 2. Problem ----------
  pres.addSection({ title: "Problem" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Problem" });
  s.addText("Every week. By hand.", { placeholder: "title" });
  // big stat
  card(s, 0.5, 1.3, 3.4, 3.6, HEX.ink, "stat card");
  T(s, "6 min", { x: 0.8, y: 1.6, w: 3, h: 1.1, fontFace: THEME.headFontFace, fontSize: 60, bold: true, color: HEX.amber });
  T(s, "to type ONE invoice\ninto Excel", { x: 0.8, y: 2.75, w: 3, h: 0.8, fontSize: 16, color: HEX.paper });
  T(s, "× every supplier, every delivery", { x: 0.8, y: 4.15, w: 3, h: 0.4, fontSize: 13, color: "9CC3B1", italic: true });
  // pain chips
  const pains = [
    [I.lang, "Arabic · French · English", "on the same paper"],
    [I.money, "LBP and USD", "one slip = 89,500× wrong"],
    [I.copy, "Double payments", "the same invoice, twice"],
  ];
  pains.forEach(([img, h, sub], i) => {
    const y = 1.3 + i * 0.82;
    circle(s, 4.3, y, 0.62, HEX.leaf, img, h);
    T(s, h, { x: 5.1, y: y + 0.02, w: 4.4, h: 0.32, fontSize: 18, bold: true, color: C.text1 });
    T(s, sub, { x: 5.1, y: y + 0.34, w: 4.4, h: 0.28, fontSize: 13, color: C.accent6 });
  });
  // voice note / real person
  card(s, 4.3, 3.85, 5.2, 1.05, HEX.mint, "voice note card");
  circle(s, 4.5, 4.05, 0.65, HEX.amber, I.mic, "voice note");
  T(s, "“[Owner's words: would they use it?]”", { x: 5.35, y: 4.0, w: 4.0, h: 0.4, fontSize: 14, italic: true, color: C.text2 });
  T(s, "— [Name], [shop], Byblos  ·  ▶ 30 s voice note", { x: 5.35, y: 4.42, w: 4.0, h: 0.3, fontSize: 12, color: C.accent6 });
  s.addNotes("Real job, real person (15 pts): name the owner, say how many invoices a week. Made in Lebanon: LBP/USD, Arabic/French. Play the 30-second voice note here.");

  // ---------- 3. Solution ----------
  pres.addSection({ title: "Solution" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Solution" });
  s.addText("The whole job, start to finish", { placeholder: "title" });
  const steps = [
    [I.camera, "Snap", "camera, phone\nor any file"],
    [I.brain, "Read", "local AI on\nthe Jetson"],
    [I.calc, "Check", "math · VAT ·\nduplicates · LBP"],
    [I.lockW, "Approve", "a human click,\nlocked in code"],
    [I.excel, "Excel", "saved + read\nback to verify"],
  ];
  const sx = 0.55, gap = 1.86;
  steps.forEach(([img, h, sub], i) => {
    const x = sx + i * gap;
    if (i < steps.length - 1) s.addShape(pres.shapes.LINE, { x: x + 1.1, y: 2.15, w: gap - 1.0, h: 0, line: { color: "B9D6C8", width: 2, dashType: "dash", endArrowType: "triangle" }, objectName: "arrow " + i });
    circle(s, x + 0.15, 1.6, 1.1, i === 3 ? HEX.coral : (i === 4 ? HEX.leaf : HEX.ink), img, h);
    T(s, h, { x: x - 0.2, y: 2.9, w: 1.8, h: 0.4, fontSize: 20, bold: true, color: C.text2, align: "center" });
    T(s, sub, { x: x - 0.2, y: 3.32, w: 1.8, h: 0.6, fontSize: 13, color: C.accent6, align: "center" });
  });
  card(s, 1.5, 4.2, 7.0, 0.6, HEX.mint, "time banner");
  T(s, [{ text: "~40 s ", options: { bold: true, color: HEX.leaf } }, { text: "from paper to ledger · no copy-paste", options: { color: C.text1 } }],
    { x: 1.5, y: 4.2, w: 7.0, h: 0.6, fontSize: 15, align: "center", valign: "middle" });
  s.addNotes("The agent does the whole job (15 pts): trigger = invoice arrives; steps = read, check, prepare rows; done = approved row in the shop's Excel ledger.");

  // ---------- 4. Video (blank) ----------
  pres.addSection({ title: "Demo video" });
  s = pres.addSlide({ masterName: "DARK", sectionTitle: "Demo video" });
  s.addNotes("Blank on purpose: insert the demo video here (Insert > Video). Live demo: the judges' 2 unseen invoices.");

  // ---------- 5. Tokens, speed, cost ----------
  pres.addSection({ title: "Numbers" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Numbers" });
  s.addText("Tokens, speed, cost", { placeholder: "title" });
  // token bar
  T(s, "ONE INVOICE =", { x: 0.5, y: 1.3, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.accent6, charSpacing: 2 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y: 1.7, w: 3.0, h: 0.62, rectRadius: 0.08, fill: { color: HEX.ink }, line: { color: HEX.ink }, objectName: "input tokens bar" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 3.6, y: 1.7, w: 1.8, h: 0.62, rectRadius: 0.08, fill: { color: HEX.amber }, line: { color: HEX.amber }, objectName: "output tokens bar" });
  T(s, "~1,000 tokens in", { x: 0.5, y: 1.7, w: 3.0, h: 0.62, fontSize: 15, bold: true, color: HEX.paper, align: "center", valign: "middle" });
  T(s, "~600 out", { x: 3.6, y: 1.7, w: 1.8, h: 0.62, fontSize: 15, bold: true, color: HEX.ink, align: "center", valign: "middle" });
  T(s, "the photo", { x: 0.5, y: 2.38, w: 3.0, h: 0.3, fontSize: 12, color: C.accent6, align: "center" });
  T(s, "the JSON", { x: 3.6, y: 2.38, w: 1.8, h: 0.3, fontSize: 12, color: C.accent6, align: "center" });
  // speeds
  const sp = [["250", "tokens/s reading"], ["20", "tokens/s writing"], ["~40 s", "per invoice"]];
  sp.forEach(([n, l], i) => {
    const x = 0.5 + i * 1.7;
    T(s, n, { x, y: 3.0, w: 1.6, h: 0.65, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: C.text2 });
    T(s, l, { x, y: 3.65, w: 1.6, h: 0.5, fontSize: 12, color: C.accent6 });
  });
  T(s, "Qwen2.5-VL 3B · runs on the Jetson GPU · no cloud", { x: 0.5, y: 4.4, w: 5, h: 0.3, fontSize: 12, italic: true, color: C.accent1 });
  // cost card
  card(s, 6.0, 1.3, 3.5, 3.6, HEX.ink, "cost card");
  T(s, "COST PER INVOICE", { x: 6.3, y: 1.5, w: 3, h: 0.3, fontSize: 12, bold: true, color: HEX.amber, charSpacing: 2 });
  T(s, "$0.0001", { x: 6.3, y: 1.85, w: 3, h: 0.75, fontFace: THEME.headFontFace, fontSize: 40, bold: true, color: HEX.paper });
  T(s, "Invoice Mate (electricity)", { x: 6.3, y: 2.6, w: 3, h: 0.3, fontSize: 13, color: "9CC3B1" });
  T(s, "$0.40", { x: 6.3, y: 3.05, w: 3, h: 0.6, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: "CFE6DA", strike: "sngStrike" });
  T(s, "a person, 6 min at $4/h", { x: 6.3, y: 3.65, w: 3, h: 0.3, fontSize: 13, color: "9CC3B1" });
  T(s, "4,000× cheaper", { x: 6.3, y: 4.2, w: 3, h: 0.45, fontSize: 20, bold: true, color: HEX.amber });
  s.addNotes("Cost per run (Twist 07): 25 W × ~40 s × $0.40/kWh ≈ $0.0001. No API bill, no per-token fee. Human: 6 minutes at $4/hour = $0.40.");

  // ---------- 6. Works every time ----------
  pres.addSection({ title: "Proof" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Proof" });
  s.addText("20 invoices, not 1 lucky run", { placeholder: "title" });
  // 20 live cases, all handled as intended (12 and 15 = duplicates, blocked on purpose)
  const DUP = { 12: 1, 15: 1 };
  for (let i = 0; i < 20; i++) {
    const n = i + 1, col = i % 5, row = Math.floor(i / 5);
    const x = 0.5 + col * 1.0, y = 1.3 + row * 0.82;
    const dup = DUP[n];
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 0.88, h: 0.7, rectRadius: 0.08,
      fill: { color: dup ? HEX.amber : HEX.leaf }, line: { color: dup ? HEX.amber : HEX.leaf }, objectName: "case " + n });
    T(s, String(n), { x, y: y + 0.04, w: 0.88, h: 0.36, fontSize: 18, bold: true, color: dup ? HEX.ink : HEX.paper, align: "center", valign: "middle" });
    T(s, dup ? "duplicate blocked" : "✓ right", { x, y: y + 0.38, w: 0.88, h: 0.28, fontSize: dup ? 8 : 10, color: dup ? HEX.ink : HEX.paper, align: "center", valign: "middle" });
  }
  T(s, "Live test on the Jetson, 15 Nov 2026: 20 real and test invoices, all handled as intended", { x: 0.5, y: 4.62, w: 4.9, h: 0.4, fontSize: 11, italic: true, color: C.accent6 });
  const proof = [["20 / 20", "handled correctly", HEX.leaf], ["2 / 2", "duplicates blocked", HEX.amber], ["0", "silent errors", HEX.ink]];
  proof.forEach(([n, l, col], i) => {
    const y = 1.3 + i * 1.15;
    card(s, 5.8, y, 3.7, 0.95, HEX.mint, "proof " + l);
    T(s, n, { x: 6.0, y, w: 1.9, h: 0.95, fontFace: THEME.headFontFace, fontSize: 28, bold: true, color: col, valign: "middle" });
    T(s, l, { x: 7.95, y, w: 1.5, h: 0.95, fontSize: 14, color: C.text1, valign: "middle" });
  });
  T(s, "Every planted error was caught and flagged before saving", { x: 5.8, y: 4.75, w: 3.7, h: 0.3, fontSize: 11, italic: true, color: C.accent6 });
  s.addNotes("Works every time (25 pts): 20 live cases on the Jetson, 20 of 20 handled as intended. 7 of 7 planted errors flagged (wrong line amounts, wrong VAT, missing date, missing number). Cases 12 and 15 are the same invoice sent again as a PDF / photo: blocked, approval refused, no double payment. 0 silent errors. All 20 are in the repo under test-cases/ and visible live at https://elevai-jetson.tailadbf60.ts.net/");

  // ---------- 7. Any format ----------
  pres.addSection({ title: "Whole job" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Whole job" });
  s.addText("However the invoice arrives", { placeholder: "title" });
  const fmts = [[I.cam, "Shop camera"], [I.phone, "Phone photo"], [I.pdf, "PDF scan"], [I.word, "Word"],
                [I.xls, "Excel / CSV"], [I.mail, "Email"], [I.zip, "ZIP"], [I.img, "iPhone HEIC"]];
  fmts.forEach(([img, l], i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = 0.5 + col * 1.5, y = 1.3 + row * 1.6;
    card(s, x, y, 1.3, 1.35, HEX.mint, "format " + l);
    s.addImage({ data: img, x: x + 0.4, y: y + 0.2, w: 0.5, h: 0.5, altText: l, objectName: "icon " + l });
    T(s, l, { x: x + 0.05, y: y + 0.82, w: 1.2, h: 0.35, fontSize: 13, bold: true, color: C.text2, align: "center" });
  });
  card(s, 6.6, 1.3, 2.9, 2.95, HEX.ink, "languages card");
  T(s, "عربي", { x: 6.8, y: 1.45, w: 2.5, h: 0.6, fontSize: 28, bold: true, color: HEX.amber });
  T(s, "Français", { x: 6.8, y: 2.05, w: 2.5, h: 0.5, fontSize: 22, bold: true, color: HEX.paper });
  T(s, "English", { x: 6.8, y: 2.55, w: 2.5, h: 0.5, fontSize: 22, bold: true, color: HEX.paper });
  T(s, "LBP ⇄ USD @ 89,500", { x: 6.8, y: 3.3, w: 2.5, h: 0.4, fontSize: 15, bold: true, color: "9CC3B1" });
  T(s, "Made for Lebanon", { x: 6.8, y: 3.7, w: 2.5, h: 0.35, fontSize: 13, italic: true, color: "9CC3B1" });
  T(s, "Lands in the tool shops already use: their Excel ledger", { x: 0.5, y: 4.55, w: 9, h: 0.35, fontSize: 14, italic: true, color: C.accent1 });
  s.addNotes("Whole job, real tools: the output is the shop's own Excel file (Invoices, Lines, Suppliers sheets). Every input format is converted on the device.");

  // ---------- 8. Secure ----------
  pres.addSection({ title: "Security" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Security" });
  s.addText("Nothing leaves the shop", { placeholder: "title" });
  const sec = [
    [I.cloudOff, HEX.ink, "100% local", "no cloud · no API key\nto leak"],
    [I.user, HEX.coral, "Human lock", "nothing is written until\nthe owner clicks Approve"],
    [I.shield, HEX.leaf, "Injection-proof", "text on the invoice is data,\nnever an order (AR · FR · EN)"],
    [I.copy, HEX.ink, "Double-pay guard", "same number · same total ·\nsame file · same photo"],
  ];
  sec.forEach(([img, col, h, sub], i) => {
    const col2 = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col2 * 4.6, y = 1.3 + row * 1.75;
    card(s, x, y, 4.4, 1.5, HEX.mint, "security " + h);
    circle(s, x + 0.25, y + 0.35, 0.8, col, img, h);
    T(s, h, { x: x + 1.3, y: y + 0.25, w: 2.9, h: 0.4, fontSize: 19, bold: true, color: C.text2 });
    T(s, sub, { x: x + 1.3, y: y + 0.68, w: 2.95, h: 0.65, fontSize: 13, color: C.accent6 });
  });
  s.addNotes("Secure and in control (15 pts) + the real lock (Twist 04): approval is enforced in code (the ledger refuses an unapproved write). Prompt injection test case included. Excel save is atomic and read back to verify.");

  // ---------- 9. Business model ----------
  pres.addSection({ title: "Business" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Business" });
  s.addText("Who pays, and why", { placeholder: "title" });
  // one product, one price: the box
  card(s, 0.5, 1.3, 5.6, 2.75, HEX.ink, "box card");
  circle(s, 0.8, 1.55, 0.8, HEX.amber, I.chip, "Invoice Mate box");
  T(s, "PAY ONCE", { x: 1.8, y: 1.6, w: 3, h: 0.3, fontSize: 13, bold: true, color: HEX.amber, charSpacing: 3 });
  T(s, "The Invoice Mate box", { x: 1.8, y: 1.92, w: 4.1, h: 0.4, fontSize: 17, bold: true, color: HEX.paper });
  T(s, "$550", { x: 0.8, y: 2.5, w: 2.6, h: 0.95, fontFace: THEME.headFontFace, fontSize: 60, bold: true, color: HEX.amber });
  T(s, [{ text: "The AI chip", options: { breakLine: true } }, { text: "+ the encrypted agent", options: { breakLine: true } }, { text: "Yours forever", options: { bold: true, color: HEX.amber } }],
    { x: 3.5, y: 2.5, w: 2.5, h: 1.0, fontSize: 14, color: "CFE6DA", valign: "middle" });
  T(s, "No subscription · no cloud · no fee per invoice", { x: 0.8, y: 3.6, w: 5.1, h: 0.3, fontSize: 12, italic: true, color: "9CC3B1" });
  // why it pays
  card(s, 6.4, 1.3, 3.1, 2.75, HEX.amber, "payback card");
  T(s, "10 invoices / day", { x: 6.65, y: 1.45, w: 2.7, h: 0.35, fontSize: 13, bold: true, color: HEX.ink });
  T(s, "$120", { x: 6.65, y: 1.85, w: 2.7, h: 0.75, fontFace: THEME.headFontFace, fontSize: 40, bold: true, color: HEX.ink });
  T(s, "of typing saved / month", { x: 6.65, y: 2.6, w: 2.7, h: 0.3, fontSize: 13, color: HEX.ink });
  T(s, "Paid back in ~5 months", { x: 6.65, y: 3.2, w: 2.7, h: 0.4, fontSize: 16, bold: true, color: HEX.ink });
  // lean start
  T(s, [{ text: "Who pays: ", options: { bold: true, color: HEX.ink } }, { text: "the shop owner, or their accountant for each client shop", options: { color: HEX.text } }],
    { x: 0.5, y: 4.3, w: 9, h: 0.35, fontSize: 15 });
  T(s, "Lean start next month: 1 box · 1 shop", { x: 0.5, y: 4.68, w: 9, h: 0.3, fontSize: 12, italic: true, color: C.accent6 });
  s.addNotes("Business model (20 pts): one-time $550 for the Invoice Mate box (Jetson AI chip + the encrypted agent), used forever: no subscription, no cloud, no per-invoice fee. Running cost: $0.0001 of electricity per invoice. Why: a shop with 10 invoices a day saves ~$120 a month of typing (6 min at $4/h each), so the box pays back in about 5 months.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch(e => { console.error(e); process.exit(1); });
