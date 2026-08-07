import { Link } from "react-router-dom";

const ROLE_CARDS = [
  {
    title: "Soori Admin",
    description: "Onboard companies, manage subscriptions and billing details.",
  },
  {
    title: "Client Admin",
    description: "Run your team's support desk — staff, customers, and reporting.",
  },
  {
    title: "Support Staff",
    description: "Handle assigned tickets, reply to customers, track resolution time.",
  },
  {
    title: "Sub-Client",
    description: "Raise a ticket, track it, and get help — no back-and-forth over email.",
  },
];

/**
 * Signature element: three separate, differently-colored "channels" —
 * each one a distinct company's tickets — visually converging into a
 * single Soori node at the bottom. This is the one thing this page is
 * built to be remembered by, and it's not decoration: it's a literal
 * picture of the actual thesis of the product (many companies, each
 * one's data completely isolated from the others, one platform
 * running underneath all of them). A generic gradient-blob hero would
 * say nothing about what Soori actually does; this says it directly.
 */
function TenantChannelsGraphic() {
  const channels = [
    { color: "#0f6b63", label: "Acme Corp" },
    { color: "#d9642c", label: "Beta LLC" },
    { color: "#5c6b6e", label: "Umbrella Inc" },
  ];

  return (
    <svg
      viewBox="0 0 480 280"
      width="100%"
      style={{ maxWidth: 440 }}
      role="img"
      aria-label="Three separate companies' ticket channels, each isolated, converging into one Soori platform"
    >
      {channels.map((ch, i) => {
        const y = 36 + i * 64;
        return (
          <g key={ch.label} className="channel-row" style={{ animationDelay: `${i * 140}ms` }}>
            <rect x="16" y={y} width="140" height="34" rx="8" fill={ch.color} opacity="0.12" />
            <rect x="16" y={y} width="4" height="34" rx="2" fill={ch.color} />
            <text x="32" y={y + 22} fontSize="13" fontWeight="600" fill="var(--ink)" fontFamily="var(--font-ui)">
              {ch.label}
            </text>
            <path
              d={`M 156 ${y + 17} C 260 ${y + 17}, 300 240, 380 240`}
              fill="none"
              stroke={ch.color}
              strokeWidth="2"
              opacity="0.55"
              className="channel-path"
              style={{ animationDelay: `${400 + i * 140}ms` }}
            />
          </g>
        );
      })}

      <rect x="368" y="216" width="96" height="48" rx="10" fill="var(--primary)" className="channel-hub" />
      <text x="416" y="245" fontSize="13" fontWeight="700" fill="white" textAnchor="middle" fontFamily="var(--font-ui)">
        Soori
      </text>
    </svg>
  );
}

export default function LandingPage() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <style>{`
        @keyframes channelRowIn {
          from { opacity: 0; transform: translateX(-12px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes channelPathIn {
          from { stroke-dashoffset: 240; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes hubIn {
          from { opacity: 0; transform: scale(0.85); }
          to { opacity: 1; transform: scale(1); }
        }
        .channel-row { opacity: 0; animation: channelRowIn 0.5s ease forwards; }
        .channel-path { stroke-dasharray: 240; stroke-dashoffset: 240; animation: channelPathIn 0.7s ease forwards; }
        .channel-hub { transform-origin: 416px 240px; opacity: 0; animation: hubIn 0.4s ease forwards; animation-delay: 850ms; }
        @media (prefers-reduced-motion: reduce) {
          .channel-row, .channel-path, .channel-hub { animation: none; opacity: 1; stroke-dashoffset: 0; }
        }
      `}</style>

      <header
        style={{
          padding: "20px 40px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: "1.15rem", letterSpacing: "-0.01em" }}>
          Soori <span style={{ color: "var(--primary)" }}>Ticketing System</span>
        </div>
        <Link to="/login" className="btn btn-primary">
          Log in
        </Link>
      </header>

      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "48px 24px 80px",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.1fr 0.9fr",
            gap: 48,
            alignItems: "center",
            maxWidth: 1040,
            width: "100%",
            marginBottom: 72,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "var(--text-hero)",
                fontWeight: 800,
                letterSpacing: "-0.02em",
                lineHeight: 1.08,
                marginBottom: 20,
              }}
            >
              One support desk.
              <br />
              Every company kept
              <br />
              <span style={{ color: "var(--primary)" }}>completely apart.</span>
            </h1>
            <p style={{ fontSize: "1.05rem", color: "var(--ink-soft)", marginBottom: 32, maxWidth: 440 }}>
              Soori runs support for many companies on one platform — while making
              sure no company ever sees another's tickets, staff, or customers.
            </p>
            <Link to="/login" className="btn btn-primary" style={{ padding: "12px 28px", fontSize: "1rem" }}>
              Log in to your account
            </Link>
          </div>

          <div style={{ display: "flex", justifyContent: "center" }}>
            <TenantChannelsGraphic />
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 16,
            width: "100%",
            maxWidth: 960,
          }}
        >
          {ROLE_CARDS.map((role) => (
            <div key={role.title} className="card" style={{ padding: 20 }}>
              <h3 style={{ fontSize: "0.95rem", marginBottom: 8 }}>{role.title}</h3>
              <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", margin: 0 }}>{role.description}</p>
            </div>
          ))}
        </div>
      </main>

      <footer style={{ padding: "20px 40px", textAlign: "center", color: "var(--ink-soft)", fontSize: "0.8rem" }}>
        Soori Ticketing System
      </footer>
    </div>
  );
}
