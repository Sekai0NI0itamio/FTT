import { defineConfig } from "electron-vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  main: {
    entry: "src/main/index.ts",
  },
  preload: {
    input: {
      index: path.join(__dirname, "src/preload/index.ts"),
    },
  },
  renderer: {
    plugins: [react()],
    resolve: {
      alias: {
        "@renderer": path.join(__dirname, "src/renderer/src"),
      },
    },
  },
});
