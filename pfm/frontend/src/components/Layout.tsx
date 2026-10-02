import { NavLink, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { api, saveTokens } from "../api";
import type { User } from "../types";
import { useEffect, useState } from "react";

const links = [
  ["/", "Dashboard"],
  ["/transactions", "Transactions"],
  ["/anomalies", "Anomalies"],
  ["/forecast", "Forecast"],
  ["/metrics", "Model metrics"],
];

export function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");

  useEffect(() => {
    api<User>("/api/v1/auth/me")
      .then((user) => setEmail(user.email))
      .catch(() => {
        saveTokens(null);
        navigate("/login");
      });
  }, [navigate]);

  return (
    <div className="shell">
      <aside className="nav">
        <p className="brand">
          Finance <span>tracker</span>
        </p>
        <p className="tagline">Income, spend, and the charges that do not look like you.</p>
        <nav>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <div>{email}</div>
          <button
            className="btn secondary"
            style={{ marginTop: 12 }}
            onClick={() => {
              saveTokens(null);
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
