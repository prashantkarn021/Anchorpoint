import { Compass } from "lucide-react";
import { createBrowserRouter, Link, RouterProvider } from "react-router";
import { Layout } from "./components/Layout";
import { buttonClass, EmptyState } from "./components/ui";
import { ActivityPage } from "./pages/ActivityPage";
import { Connections } from "./pages/Connections";
import { Overview } from "./pages/Overview";
import { Packet } from "./pages/Packet";
import { Privacy } from "./pages/Privacy";
import { Records } from "./pages/Records";
import { RiskCheck } from "./pages/RiskCheck";
import { Timeline } from "./pages/Timeline";

function NotFound() {
  return (
    <EmptyState
      icon={Compass}
      title="Page not found"
      body="That page doesn't exist."
      action={
        <Link to="/" className={buttonClass("secondary", "sm")}>
          Back to overview
        </Link>
      }
    />
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "records", element: <Records /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "risk-check", element: <RiskCheck /> },
      { path: "timeline", element: <Timeline /> },
      { path: "packet", element: <Packet /> },
      { path: "connections", element: <Connections /> },
      { path: "privacy", element: <Privacy /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
