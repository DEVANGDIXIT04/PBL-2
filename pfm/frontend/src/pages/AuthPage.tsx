import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, saveTokens } from "../api";
import type { Tokens } from "../types";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("Demo1234!");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const tokens = await api<Tokens>(`/api/v1/auth/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveTokens(tokens);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={onSubmit}>
        <p className="brand">
          Finance <span>tracker</span>
        </p>
        <h1>{mode === "login" ? "Welcome back" : "Create an account"}</h1>
        <p className="sub">Income, spend, and the transactions that do not look like you.</p>
        {error && <div className="error">{error}</div>}
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          minLength={8}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        <div className="modal-actions row">
          <button className="btn" disabled={busy} type="submit">
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
          {mode === "login" ? (
            <Link to="/register">Need an account?</Link>
          ) : (
            <Link to="/login">Already registered?</Link>
          )}
        </div>
        <p className="note">Demo login after seeding: demo@example.com / Demo1234!</p>
      </form>
    </div>
  );
}
