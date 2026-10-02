import { Navigate, Route, Routes } from "react-router-dom";
import { hasSession } from "./api";
import { Layout } from "./components/Layout";
import { Anomalies } from "./pages/Anomalies";
import { AuthPage } from "./pages/AuthPage";
import { Dashboard } from "./pages/Dashboard";
import { Forecast } from "./pages/Forecast";
import { Metrics } from "./pages/Metrics";
import { Transactions } from "./pages/Transactions";

function Private({ children }: { children: JSX.Element }) {
  if (!hasSession()) return <Navigate to="/login" replace />;
  return children;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route
        path="/*"
        element={
          <Private>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/transactions" element={<Transactions />} />
                <Route path="/anomalies" element={<Anomalies />} />
                <Route path="/forecast" element={<Forecast />} />
                <Route path="/metrics" element={<Metrics />} />
              </Routes>
            </Layout>
          </Private>
        }
      />
    </Routes>
  );
}
