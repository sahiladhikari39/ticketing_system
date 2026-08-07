import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { startIframeHeightReporting } from "./utils/iframeEmbed";
import "./styles/global.css";
import "./styles/badges.css";
import "./styles/layout.css";
import "./styles/components.css";

startIframeHeightReporting();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
