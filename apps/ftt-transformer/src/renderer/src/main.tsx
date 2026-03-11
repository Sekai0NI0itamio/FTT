import React from "react";
import { createRoot } from "react-dom/client";
import App from "@renderer/App";
import "@renderer/styles.css";

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<App />);
}
