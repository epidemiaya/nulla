import { useState, useEffect, useCallback, useRef } from "react";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:       "#080808",
  surface:  "#0d0d0d",
  surface2: "#131313",
  border:   "rgba(255,255,255,0.07)",
  accent:   "#00e5a0",
  accentDim:"rgba(0,229,160,0.12)",
  text:     "#d4d4d4",
  muted:    "#4a4a4a",
  red:      "#ff5252",
  yellow:   "#ffd166",
  green:    "#00e5a0",
  font:     "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
};

// ── Utility helpers ───────────────────────────────────────────────────────────
const trunc = (s = "", l = 12, r = 8) =>
  s.length > l + r + 3 ? `${s.slice(0, l)}…${s.slice(-r)}` : s;

const copyText = (text) => {
  navigator.clipboard?.writeText(text).catch(() => {});
};

const formatLAC = (n) => {
  if (n === undefined || n === null) return "—";
  const v = parseFloat(n);
  if (isNaN(v)) return "—";
  if (v >= 1000) return `${v.toLocaleString("en", { maximumFractionDigits: 2 })} LAC`;
  return `${v.toFixed(4)} LAC`;
};

const fmtDate = (ts) => {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString("en", { month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false });
};

// ── API client ────────────────────────────────────────────────────────────────
const api = async (path, body) => {
  const opts = {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    opts.method = "POST";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(`/api${path}`, opts);
  return r.json();
};

// ── Global CSS ────────────────────────────────────────────────────────────────
const GLOBAL_CSS = `
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: ${T.bg};
  color: ${T.text};
  font-family: ${T.font};
  font-size: 13px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  overflow-x: hidden;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: ${T.muted}; border-radius: 2px; }

::selection { background: ${T.accentDim}; color: ${T.accent}; }

input, textarea {
  font-family: ${T.font};
  background: ${T.surface2};
  border: 1px solid ${T.border};
  color: ${T.text};
  border-radius: 4px;
  padding: 10px 12px;
  font-size: 13px;
  width: 100%;
  outline: none;
  transition: border-color 0.15s;
}

input:focus, textarea:focus {
  border-color: ${T.accent};
  box-shadow: 0 0 0 2px ${T.accentDim};
}

textarea { resize: vertical; min-height: 72px; }

button {
  font-family: ${T.font};
  cursor: pointer;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  transition: opacity 0.15s, transform 0.1s;
}

button:active { transform: scale(0.97); }
button:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.fade-in { animation: fadeIn 0.2s ease forwards; }
.spinner { animation: spin 0.8s linear infinite; display: inline-block; }
`;

// ── Base components ───────────────────────────────────────────────────────────

const Btn = ({ children, onClick, variant = "primary", disabled, style, ...p }) => {
  const styles = {
    primary: { background: T.accent, color: "#000", fontWeight: 600, padding: "10px 20px" },
    ghost:   { background: "transparent", color: T.text, border: `1px solid ${T.border}`, padding: "10px 20px" },
    danger:  { background: "transparent", color: T.red, border: `1px solid ${T.red}33`, padding: "10px 20px" },
    link:    { background: "transparent", color: T.accent, padding: "4px 0", fontWeight: 400 },
  };
  return (
    <button onClick={onClick} disabled={disabled}
      style={{ ...styles[variant], letterSpacing: "0.04em", ...style }} {...p}>
      {children}
    </button>
  );
};

const Card = ({ children, style }) => (
  <div style={{
    background: T.surface,
    border: `1px solid ${T.border}`,
    borderRadius: 6,
    padding: "16px 18px",
    ...style,
  }}>{children}</div>
);

const Label = ({ children }) => (
  <div style={{ color: T.muted, fontSize: 11, letterSpacing: "0.1em",
    textTransform: "uppercase", marginBottom: 6 }}>
    {children}
  </div>
);

const Dot = ({ on, color }) => (
  <span style={{
    display: "inline-block", width: 7, height: 7, borderRadius: "50%",
    background: on ? (color || T.accent) : T.muted,
    boxShadow: on ? `0 0 5px ${color || T.accent}` : "none",
    marginRight: 6,
  }} />
);

const CopyField = ({ value, label }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    copyText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div>
      {label && <Label>{label}</Label>}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}
        onClick={copy} title="Click to copy" role="button"
        style={{ cursor: "pointer" }}>
        <div style={{
          flex: 1, background: T.surface2, border: `1px solid ${T.border}`,
          borderRadius: 4, padding: "8px 12px", fontSize: 12,
          color: T.muted, wordBreak: "break-all", lineHeight: 1.5,
          transition: "border-color 0.15s",
        }}
          onClick={copy}>{value}</div>
        <Btn variant="ghost" onClick={copy} style={{ flexShrink: 0, padding: "8px 12px", fontSize: 12 }}>
          {copied ? "✓" : "copy"}
        </Btn>
      </div>
    </div>
  );
};

const ErrBox = ({ msg }) =>
  msg ? (
    <div style={{
      background: `${T.red}11`, border: `1px solid ${T.red}33`,
      borderRadius: 4, padding: "10px 12px", color: T.red,
      fontSize: 12, marginTop: 10,
    }}>{msg}</div>
  ) : null;

const Spinner = () => (
  <span className="spinner" style={{ display: "inline-block", width: 14, height: 14,
    border: `2px solid ${T.muted}`, borderTopColor: T.accent,
    borderRadius: "50%" }} />
);

const Field = ({ label, ...props }) => (
  <div style={{ marginBottom: 14 }}>
    {label && <Label>{label}</Label>}
    <input {...props} />
  </div>
);

// ── Screens ───────────────────────────────────────────────────────────────────

// ── SETUP: landing when no wallet ─────────────────────────────────────────────
function ScreenSetup({ onCreated, onImported }) {
  const [view, setView] = useState("home"); // home | create | import
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [mnemonic, setMnemonic] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [step, setStep] = useState(1); // 1=password, 2=show mnemonic

  const doCreate = async () => {
    if (pw.length < 8) return setError("Min 8 characters");
    if (pw !== pw2) return setError("Passwords don't match");
    setLoading(true); setError("");
    const r = await api("/wallet/create", { password: pw });
    setLoading(false);
    if (!r.ok) return setError(r.error);
    setCreated(r);
    setStep(2);
  };

  const doImport = async () => {
    if (!mnemonic.trim()) return setError("Enter mnemonic");
    if (pw.length < 8) return setError("Min 8 characters");
    if (pw !== pw2) return setError("Passwords don't match");
    setLoading(true); setError("");
    const r = await api("/wallet/import", { mnemonic: mnemonic.trim(), password: pw });
    setLoading(false);
    if (!r.ok) return setError(r.error);
    onImported(r.key_id);
  };

  const words = created?.mnemonic?.split(" ") || [];

  if (view === "home") return (
    <div className="fade-in" style={{ padding: "60px 24px 24px", maxWidth: 420, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <div style={{ fontSize: 11, letterSpacing: "0.25em", color: T.muted, marginBottom: 10 }}>
          LAC LIGHT WALLET
        </div>
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.02em",
          color: T.accent }}>NULLA</div>
        <div style={{ color: T.muted, fontSize: 12, marginTop: 8 }}>
          Privacy-first. Keys stay local.
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Btn onClick={() => setView("create")} style={{ width: "100%", padding: "14px" }}>
          CREATE NEW WALLET
        </Btn>
        <Btn variant="ghost" onClick={() => setView("import")} style={{ width: "100%", padding: "14px" }}>
          IMPORT FROM MNEMONIC
        </Btn>
      </div>
      <div style={{ textAlign: "center", marginTop: 32, color: T.muted, fontSize: 11, lineHeight: 1.8 }}>
        Your keys never leave this device.<br />
        No accounts. No tracking. No servers.
      </div>
    </div>
  );

  if (view === "create") {
    if (step === 2 && created) return (
      <div className="fade-in" style={{ padding: "24px", maxWidth: 420, margin: "0 auto" }}>
        <div style={{ color: T.accent, fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
          ✓ Wallet created
        </div>
        <div style={{ color: T.muted, fontSize: 12, marginBottom: 20 }}>
          Write down your recovery phrase. It's the only way to restore your wallet.
        </div>
        <div style={{
          background: T.surface2, border: `1px solid ${T.yellow}33`,
          borderRadius: 6, padding: 16, marginBottom: 20,
        }}>
          <div style={{ color: T.yellow, fontSize: 11, letterSpacing: "0.1em",
            marginBottom: 12 }}>⚠ RECOVERY PHRASE — KEEP OFFLINE</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "6px 16px" }}>
            {words.map((w, i) => (
              <div key={i} style={{ fontSize: 13 }}>
                <span style={{ color: T.muted, fontSize: 10, marginRight: 4 }}>{i + 1}.</span>
                {w}
              </div>
            ))}
          </div>
        </div>
        <CopyField value={created.mnemonic} label="Copy full phrase" />
        <div style={{ marginTop: 16 }}>
          <CopyField value={created.key_id} label="Your Key ID (address)" />
        </div>
        <Btn style={{ width: "100%", marginTop: 20, padding: 14 }}
          onClick={() => onCreated(created.key_id)}>
          I SAVED MY PHRASE — OPEN WALLET
        </Btn>
      </div>
    );
    return (
      <div className="fade-in" style={{ padding: "24px", maxWidth: 420, margin: "0 auto" }}>
        <button onClick={() => setView("home")} style={{ background: "none", color: T.muted,
          fontSize: 12, marginBottom: 20, cursor: "pointer" }}>← back</button>
        <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>Create wallet</div>
        <div style={{ color: T.muted, fontSize: 12, marginBottom: 20 }}>
          Set a strong password to encrypt your keystore.
        </div>
        <Field label="Password (min 8 chars)" type="password" value={pw}
          onChange={e => setPw(e.target.value)} placeholder="••••••••••••" />
        <Field label="Confirm password" type="password" value={pw2}
          onChange={e => setPw2(e.target.value)} placeholder="••••••••••••" />
        <ErrBox msg={error} />
        <Btn style={{ width: "100%", marginTop: 16, padding: 14 }}
          onClick={doCreate} disabled={loading}>
          {loading ? <Spinner /> : "GENERATE WALLET"}
        </Btn>
      </div>
    );
  }

  if (view === "import") return (
    <div className="fade-in" style={{ padding: "24px", maxWidth: 420, margin: "0 auto" }}>
      <button onClick={() => setView("home")} style={{ background: "none", color: T.muted,
        fontSize: 12, marginBottom: 20, cursor: "pointer" }}>← back</button>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>Import wallet</div>
      <div style={{ color: T.muted, fontSize: 12, marginBottom: 20 }}>
        Enter your 24-word recovery phrase.
      </div>
      <div style={{ marginBottom: 14 }}>
        <Label>Mnemonic phrase</Label>
        <textarea value={mnemonic} onChange={e => setMnemonic(e.target.value)}
          placeholder="word1 word2 word3 ... word24" rows={4} />
      </div>
      <Field label="New password" type="password" value={pw}
        onChange={e => setPw(e.target.value)} placeholder="••••••••••••" />
      <Field label="Confirm password" type="password" value={pw2}
        onChange={e => setPw2(e.target.value)} placeholder="••••••••••••" />
      <ErrBox msg={error} />
      <Btn style={{ width: "100%", marginTop: 16, padding: 14 }}
        onClick={doImport} disabled={loading}>
        {loading ? <Spinner /> : "RESTORE WALLET"}
      </Btn>
    </div>
  );
}

// ── UNLOCK ────────────────────────────────────────────────────────────────────
function ScreenUnlock({ onUnlocked }) {
  const [pw, setPw] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const ref = useRef();

  useEffect(() => { ref.current?.focus(); }, []);

  const doUnlock = async () => {
    if (!pw) return;
    setLoading(true); setError("");
    const r = await api("/wallet/unlock", { password: pw });
    setLoading(false);
    if (!r.ok) return setError(r.error);
    onUnlocked(r.key_id);
  };

  return (
    <div className="fade-in" style={{ padding: "80px 24px 24px", maxWidth: 380, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <div style={{ fontSize: 28, fontWeight: 700, color: T.accent, letterSpacing: "-0.02em" }}>
          NULLA
        </div>
        <div style={{ color: T.muted, fontSize: 12, marginTop: 6 }}>Enter password to unlock</div>
      </div>
      <Field label="" type="password" value={pw} ref={ref}
        onChange={e => setPw(e.target.value)}
        onKeyDown={e => e.key === "Enter" && doUnlock()}
        placeholder="Password" />
      <ErrBox msg={error} />
      <Btn style={{ width: "100%", marginTop: 12, padding: 14 }}
        onClick={doUnlock} disabled={loading || !pw}>
        {loading ? <Spinner /> : "UNLOCK"}
      </Btn>
    </div>
  );
}

// ── DASHBOARD ─────────────────────────────────────────────────────────────────
function ScreenDashboard({ wallet, onNav }) {
  const [bal, setBal] = useState(null);
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    const [b, t] = await Promise.all([
      api("/balance"),
      api("/transactions?limit=5"),
    ]);
    if (b.ok) setBal(b);
    if (t.ok) setTxs(t.transactions || []);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, []);

  return (
    <div className="fade-in" style={{ padding: "0 0 80px" }}>
      {/* Balance hero */}
      <div style={{
        background: `linear-gradient(180deg, ${T.surface} 0%, ${T.bg} 100%)`,
        borderBottom: `1px solid ${T.border}`,
        padding: "28px 24px 24px",
        textAlign: "center",
      }}>
        <div style={{ color: T.muted, fontSize: 11, letterSpacing: "0.12em", marginBottom: 12 }}>
          AVAILABLE BALANCE
        </div>
        {loading ? (
          <div style={{ fontSize: 32, color: T.muted }}><Spinner /></div>
        ) : (
          <div style={{ fontSize: 34, fontWeight: 700, color: T.accent,
            letterSpacing: "-0.02em", lineHeight: 1 }}>
            {formatLAC(bal?.balance)}
          </div>
        )}
        {bal?.username && (
          <div style={{ color: T.muted, fontSize: 12, marginTop: 8 }}>
            @{bal.username}
          </div>
        )}
        {bal?.level > 0 && (
          <div style={{ display: "inline-block", background: T.accentDim,
            color: T.accent, fontSize: 10, letterSpacing: "0.1em",
            padding: "2px 8px", borderRadius: 12, marginTop: 8 }}>
            LVL {bal.level}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div style={{ display: "flex", gap: 10, padding: "16px 16px 0" }}>
        <Btn onClick={() => onNav("send")} style={{ flex: 1, padding: 12 }}>
          ↑ SEND
        </Btn>
        <Btn variant="ghost" onClick={() => onNav("receive")} style={{ flex: 1, padding: 12 }}>
          ↓ RECEIVE
        </Btn>
      </div>

      {/* Address */}
      <div style={{ padding: "16px" }}>
        <Card>
          <Label>KEY ID (YOUR ADDRESS)</Label>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ flex: 1, color: T.muted, fontSize: 11, wordBreak: "break-all",
              lineHeight: 1.6 }}>
              {wallet?.key_id || "—"}
            </div>
            <Btn variant="ghost" onClick={() => copyText(wallet?.key_id)}
              style={{ flexShrink: 0, padding: "6px 10px", fontSize: 11 }}>
              copy
            </Btn>
          </div>
        </Card>
      </div>

      {/* Recent transactions */}
      <div style={{ padding: "0 16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between",
          alignItems: "center", marginBottom: 10 }}>
          <Label>RECENT</Label>
          {txs.length > 0 && (
            <button onClick={() => onNav("history")}
              style={{ background: "none", color: T.muted, fontSize: 11, cursor: "pointer" }}>
              all →
            </button>
          )}
        </div>
        {loading ? (
          <div style={{ textAlign: "center", padding: 24, color: T.muted }}><Spinner /></div>
        ) : txs.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 12, textAlign: "center",
            padding: "20px 0" }}>No transactions yet</div>
        ) : (
          txs.map((tx, i) => <TxRow key={i} tx={tx} />)
        )}
      </div>
    </div>
  );
}

// ── TX ROW ────────────────────────────────────────────────────────────────────
function TxRow({ tx }) {
  const isIn = tx.direction === "in";
  const counterpart = isIn
    ? (tx.from || tx.sender || "")
    : (tx.to || tx.recipient || "");

  return (
    <div style={{
      display: "flex", alignItems: "center",
      padding: "10px 14px",
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 5, marginBottom: 6,
    }}>
      <div style={{
        width: 30, height: 30, borderRadius: "50%",
        background: isIn ? "rgba(0,229,160,0.1)" : "rgba(255,82,82,0.1)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, marginRight: 12, flexShrink: 0,
      }}>
        {isIn ? "↓" : "↑"}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: T.muted, whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis" }}>
          {isIn ? "from " : "to "}{trunc(counterpart, 10, 6)}
        </div>
        {tx.memo && (
          <div style={{ fontSize: 11, color: T.muted, marginTop: 2 }}>
            {tx.memo}
          </div>
        )}
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontWeight: 600, color: isIn ? T.green : T.red, fontSize: 13 }}>
          {isIn ? "+" : "-"}{formatLAC(tx.amount)}
        </div>
        <div style={{ fontSize: 10, color: T.muted, marginTop: 2 }}>
          {fmtDate(tx.timestamp)}
        </div>
      </div>
    </div>
  );
}

// ── SEND ──────────────────────────────────────────────────────────────────────
function ScreenSend({ wallet }) {
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [fee, setFee] = useState("0.001");
  const [memo, setMemo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);
  const [confirm, setConfirm] = useState(false);

  const total = (parseFloat(amount) || 0) + (parseFloat(fee) || 0);

  const validate = () => {
    if (!to.trim()) return "Enter recipient address or @username";
    if (!amount || parseFloat(amount) <= 0) return "Enter valid amount";
    return null;
  };

  const doSend = async () => {
    const e = validate();
    if (e) return setError(e);
    if (!confirm) { setConfirm(true); return; }

    setLoading(true); setError("");
    const r = await api("/send", {
      to: to.trim(), amount: parseFloat(amount),
      fee: parseFloat(fee), memo,
    });
    setLoading(false);
    if (!r.ok) { setConfirm(false); return setError(r.error); }
    setSuccess(r.result);
  };

  if (success) return (
    <div className="fade-in" style={{ padding: "60px 24px", maxWidth: 400, margin: "0 auto",
      textAlign: "center" }}>
      <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
      <div style={{ color: T.accent, fontWeight: 700, fontSize: 18, marginBottom: 8 }}>
        Transaction sent
      </div>
      <div style={{ color: T.muted, fontSize: 12, marginBottom: 24 }}>
        {formatLAC(amount)} → {trunc(to, 10, 8)}
      </div>
      <Btn onClick={() => { setSuccess(null); setTo(""); setAmount(""); setMemo("");
        setConfirm(false); }} style={{ width: "100%" }}>
        SEND ANOTHER
      </Btn>
    </div>
  );

  return (
    <div className="fade-in" style={{ padding: "24px", maxWidth: 420, margin: "0 auto" }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 20 }}>Send LAC</div>

      <Field label="Recipient" value={to} onChange={e => { setTo(e.target.value); setConfirm(false); }}
        placeholder="key_id (64 hex) or @username" />
      <Field label="Amount (LAC)" type="number" value={amount} min="0" step="0.0001"
        onChange={e => { setAmount(e.target.value); setConfirm(false); }}
        placeholder="0.0000" />
      <div style={{ display: "flex", gap: 10 }}>
        <div style={{ flex: 1 }}>
          <Field label="Fee" type="number" value={fee} min="0" step="0.0001"
            onChange={e => setFee(e.target.value)} placeholder="0.001" />
        </div>
      </div>
      <Field label="Memo (optional)" value={memo} onChange={e => setMemo(e.target.value)}
        placeholder="optional note" />

      {confirm && !error && (
        <Card style={{ marginBottom: 14, borderColor: `${T.yellow}44` }}>
          <div style={{ color: T.yellow, fontSize: 12, marginBottom: 8 }}>⚠ Confirm transaction</div>
          <div style={{ fontSize: 12, color: T.muted, lineHeight: 2 }}>
            <div>To: <span style={{ color: T.text }}>{trunc(to, 12, 8)}</span></div>
            <div>Amount: <span style={{ color: T.text, fontWeight: 600 }}>{formatLAC(amount)}</span></div>
            <div>Fee: <span style={{ color: T.text }}>{formatLAC(fee)}</span></div>
            <div>Total: <span style={{ color: T.accent, fontWeight: 700 }}>{formatLAC(total)}</span></div>
          </div>
        </Card>
      )}

      <ErrBox msg={error} />

      <Btn style={{ width: "100%", marginTop: 8, padding: 14 }}
        onClick={doSend} disabled={loading}>
        {loading ? <Spinner /> : confirm ? "CONFIRM & SEND" : "REVIEW TRANSACTION →"}
      </Btn>
      {confirm && (
        <Btn variant="ghost" onClick={() => setConfirm(false)}
          style={{ width: "100%", marginTop: 8, padding: 12 }}>
          CANCEL
        </Btn>
      )}
    </div>
  );
}

// ── RECEIVE ───────────────────────────────────────────────────────────────────
function ScreenReceive({ wallet }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    copyText(wallet?.key_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fade-in" style={{ padding: "24px", maxWidth: 420, margin: "0 auto" }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 20 }}>Receive LAC</div>

      {/* Visual address block */}
      <Card style={{ textAlign: "center", padding: "28px 20px", marginBottom: 16 }}>
        <div style={{
          width: 80, height: 80, borderRadius: "50%",
          background: T.accentDim,
          border: `2px solid ${T.accent}44`,
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 20px",
          fontSize: 28, color: T.accent,
        }}>↓</div>
        <div style={{ fontSize: 10, color: T.muted, letterSpacing: "0.12em",
          marginBottom: 10 }}>YOUR KEY ID</div>
        <div style={{
          fontSize: 12, wordBreak: "break-all", lineHeight: 1.8,
          color: T.text, letterSpacing: "0.04em",
        }}>
          {wallet?.key_id}
        </div>
      </Card>

      <Btn onClick={copy} style={{ width: "100%", padding: 14 }}>
        {copied ? "✓ COPIED" : "COPY ADDRESS"}
      </Btn>

      <div style={{ marginTop: 20, padding: "12px 16px",
        background: T.surface2, borderRadius: 5,
        color: T.muted, fontSize: 11, lineHeight: 1.8 }}>
        Share this address to receive LAC.<br />
        Only send LAC (LightAnonChain) tokens to this address.
      </div>
    </div>
  );
}

// ── HISTORY ───────────────────────────────────────────────────────────────────
function ScreenHistory({ wallet }) {
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 25;

  const load = async (o = 0) => {
    setLoading(true);
    const r = await api(`/transactions?limit=${LIMIT}&offset=${o}`);
    if (r.ok) setTxs(o === 0 ? (r.transactions || []) : t => [...t, ...(r.transactions || [])]);
    setLoading(false);
  };

  useEffect(() => { load(0); }, []);

  return (
    <div className="fade-in" style={{ padding: "0 0 80px" }}>
      <div style={{ padding: "16px 16px 8px", fontWeight: 700, fontSize: 15 }}>
        History
      </div>
      {loading && txs.length === 0 ? (
        <div style={{ textAlign: "center", padding: 40, color: T.muted }}><Spinner /></div>
      ) : txs.length === 0 ? (
        <div style={{ textAlign: "center", padding: 40, color: T.muted, fontSize: 12 }}>
          No transactions found
        </div>
      ) : (
        <div style={{ padding: "0 12px" }}>
          {txs.map((tx, i) => <TxRow key={i} tx={tx} />)}
          {txs.length >= LIMIT && (
            <Btn variant="ghost" onClick={() => { const o = offset + LIMIT; setOffset(o); load(o); }}
              style={{ width: "100%", marginTop: 8 }} disabled={loading}>
              {loading ? <Spinner /> : "LOAD MORE"}
            </Btn>
          )}
        </div>
      )}
    </div>
  );
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
function ScreenSettings({ wallet, onLocked }) {
  const [nodeUrl, setNodeUrl] = useState("");
  const [nodeStatus, setNodeStatus] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/node/status").then(r => {
      if (r.ok) {
        setNodeStatus(r);
        setNodeUrl(r.node_url || "");
      }
    });
  }, []);

  const testNode = async () => {
    setConnecting(true); setError("");
    const r = await api("/node/connect", { url: nodeUrl });
    setConnecting(false);
    if (!r.ok) return setError(r.error);
    setNodeStatus(r);
  };

  const doLock = async () => {
    await api("/wallet/lock", {});
    onLocked();
  };

  return (
    <div className="fade-in" style={{ padding: "24px 16px 80px", maxWidth: 420, margin: "0 auto" }}>
      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 20 }}>Settings</div>

      {/* Wallet info */}
      <Card style={{ marginBottom: 16 }}>
        <Label>WALLET</Label>
        <div style={{ fontSize: 12, color: T.muted, lineHeight: 2 }}>
          <div>Key ID</div>
          <div style={{ fontSize: 11, wordBreak: "break-all", color: T.text, marginBottom: 8 }}>
            {wallet?.key_id}
          </div>
        </div>
      </Card>

      {/* Node */}
      <Card style={{ marginBottom: 16 }}>
        <Label>NODE CONNECTION</Label>
        {nodeStatus && (
          <div style={{ display: "flex", alignItems: "center", marginBottom: 12, gap: 8 }}>
            <Dot on={nodeStatus.is_connected} />
            <span style={{ fontSize: 12, color: nodeStatus.is_connected ? T.accent : T.red }}>
              {nodeStatus.is_connected
                ? `connected · ${nodeStatus.latency_ms}ms · block ${nodeStatus.block_height}`
                : "disconnected"}
            </span>
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <input value={nodeUrl} onChange={e => setNodeUrl(e.target.value)}
            placeholder="https://lac-beta.uk"
            style={{ flex: 1 }} />
          <Btn variant="ghost" onClick={testNode} disabled={connecting}
            style={{ flexShrink: 0, padding: "10px 14px" }}>
            {connecting ? <Spinner /> : "test"}
          </Btn>
        </div>
        <ErrBox msg={error} />
      </Card>

      {/* Lock */}
      <Card>
        <Label>SECURITY</Label>
        <div style={{ color: T.muted, fontSize: 12, marginBottom: 14 }}>
          Lock the wallet to clear keys from memory.
        </div>
        <Btn variant="danger" onClick={doLock} style={{ width: "100%" }}>
          LOCK WALLET
        </Btn>
      </Card>

      <div style={{ marginTop: 24, textAlign: "center", color: T.muted, fontSize: 11 }}>
        Nulla v1.0.0 — LAC Light Client
      </div>
    </div>
  );
}

// ── NAVIGATION ────────────────────────────────────────────────────────────────
const NAV = [
  { id: "dashboard", label: "Home",    icon: "◈" },
  { id: "send",      label: "Send",    icon: "↑" },
  { id: "receive",   label: "Receive", icon: "↓" },
  { id: "history",   label: "Txns",    icon: "≡" },
  { id: "settings",  label: "Config",  icon: "⚙" },
];

function BottomNav({ active, onChange }) {
  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0,
      background: T.surface,
      borderTop: `1px solid ${T.border}`,
      display: "flex",
      zIndex: 100,
      paddingBottom: "env(safe-area-inset-bottom)",
    }}>
      {NAV.map(n => (
        <button key={n.id} onClick={() => onChange(n.id)}
          style={{
            flex: 1, padding: "12px 0",
            background: "transparent",
            color: active === n.id ? T.accent : T.muted,
            display: "flex", flexDirection: "column",
            alignItems: "center", gap: 3,
            borderTop: active === n.id ? `2px solid ${T.accent}` : "2px solid transparent",
            transition: "color 0.15s",
          }}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>{n.icon}</span>
          <span style={{ fontSize: 9, letterSpacing: "0.08em" }}>{n.label}</span>
        </button>
      ))}
    </div>
  );
}

function Header({ wallet, nodeOk }) {
  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 99,
      background: T.bg,
      borderBottom: `1px solid ${T.border}`,
      display: "flex", alignItems: "center",
      padding: "12px 16px",
      paddingTop: "calc(12px + env(safe-area-inset-top))",
    }}>
      <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "0.1em",
        color: T.accent, flex: 1 }}>NULLA</span>
      <span style={{ fontSize: 11, color: T.muted, display: "flex",
        alignItems: "center" }}>
        <Dot on={nodeOk} />
        {nodeOk ? "online" : "offline"}
      </span>
    </div>
  );
}

// ── ROOT APP ──────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("loading");
  const [tab, setTab] = useState("dashboard");
  const [wallet, setWallet] = useState(null);  // {key_id}
  const [nodeOk, setNodeOk] = useState(false);

  // Inject global CSS + Google Font
  useEffect(() => {
    const style = document.createElement("style");
    style.textContent = GLOBAL_CSS;
    document.head.appendChild(style);

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap";
    document.head.appendChild(link);

    document.body.style.background = T.bg;
    document.documentElement.style.background = T.bg;

    return () => {
      document.head.removeChild(style);
      if (document.head.contains(link)) document.head.removeChild(link);
    };
  }, []);

  // Initial status check
  useEffect(() => {
    (async () => {
      const r = await api("/status");
      if (r.wallet_unlocked) {
        const info = await api("/wallet/info");
        if (info.ok) {
          setWallet({ key_id: info.key_id });
          setScreen("app");
        } else {
          setScreen(r.wallet_exists ? "unlock" : "setup");
        }
      } else {
        setScreen(r.wallet_exists ? "unlock" : "setup");
      }
      // Node status
      const ns = await api("/node/status");
      setNodeOk(ns.is_connected || false);
    })();
  }, []);

  const onCreated = (key_id) => { setWallet({ key_id }); setScreen("app"); setTab("dashboard"); };
  const onUnlocked = (key_id) => { setWallet({ key_id }); setScreen("app"); setTab("dashboard"); };
  const onLocked = () => { setWallet(null); setScreen("unlock"); };

  if (screen === "loading") return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "100vh", color: T.accent, flexDirection: "column", gap: 16 }}>
      <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "0.1em" }}>NULLA</div>
      <Spinner />
    </div>
  );

  if (screen === "setup") return (
    <div style={{ minHeight: "100vh", background: T.bg }}>
      <ScreenSetup onCreated={onCreated} onImported={onCreated} />
    </div>
  );

  if (screen === "unlock") return (
    <div style={{ minHeight: "100vh", background: T.bg }}>
      <ScreenUnlock onUnlocked={onUnlocked} />
    </div>
  );

  // App shell
  return (
    <div style={{ minHeight: "100vh", background: T.bg, maxWidth: 480,
      margin: "0 auto", position: "relative" }}>
      <Header wallet={wallet} nodeOk={nodeOk} />
      <div style={{ paddingBottom: 60 }}>
        {tab === "dashboard" && <ScreenDashboard wallet={wallet} onNav={setTab} />}
        {tab === "send"      && <ScreenSend wallet={wallet} />}
        {tab === "receive"   && <ScreenReceive wallet={wallet} />}
        {tab === "history"   && <ScreenHistory wallet={wallet} />}
        {tab === "settings"  && <ScreenSettings wallet={wallet} onLocked={onLocked} />}
      </div>
      <BottomNav active={tab} onChange={setTab} />
    </div>
  );
}
